"""Tareas que corren en SEGUNDO PLANO (worker de django-q2), no en el webhook.

El webhook solo valida, deduplica y encola; el trabajo lento (IA, descargas,
envío de respuestas) vive aquí. Así Meta recibe su 200 en milisegundos.

OJO: el worker carga este código al arrancar. Si lo cambias, reinicia qcluster.
"""
import logging
import string
import unicodedata
from dataclasses import dataclass
from datetime import datetime

import anthropic
from django.conf import settings
from django.utils import timezone
from pydantic import ValidationError

from comprobantes.extractor import detectar_media_type, extraer
from comprobantes.interprete import interpretar
from finanzas.models import Transaccion, Usuario
from finanzas.resumenes import DIAS, calcular_resumen, formatear_resumen
from finanzas.servicios import (
    LIMA,
    OpcionInvalida,
    asignar_categoria,
    categorias_disponibles,
    deshacer_transaccion,
    formatear_transaccion,
    obtener_usuario,
    registrar_comprobante,
    registrar_movimientos_texto,
    soles,
)
from panel.servicios import cerrar_sesiones, crear_enlace

from .client import (
    MediaDemasiadoGrande,
    descargar_media,
    enviar_botones,
    enviar_lista,
    enviar_texto,
)

logger = logging.getLogger(__name__)

NO_ES_YAPE = (
    "🤔 Eso no parece un comprobante de Yape.\n"
    "Mándame la captura, o usa *Compartir* desde Yape y elígeme."
)
NO_PUDE_LEER = "😕 No pude leer bien esa captura. ¿Me la mandas de nuevo?"
OPCION_INVALIDA = "🤷 No encontré ese movimiento. Puede que ya lo hayas borrado."
FALLA_IA = "⚠️ Tuve un problema con la IA. Inténtalo en unos minutos."
AYUDA = (
    "👋 Esto es lo que sé hacer:\n\n"
    "📷 Mándame una captura de Yape (o usa *Compartir* → yo) y la anoto.\n\n"
    "✍️ O escríbeme tus gastos e ingresos:\n"
    "• _gasté 2.50 en papitas_\n"
    "• _ayer 15 de almuerzo y 8 de taxi_\n"
    "• _me pagaron 50 por un trabajo_\n\n"
    "📊 Para ver cómo vas:\n"
    "• *hoy* → lo de hoy\n"
    "• *semana* → de lunes a hoy\n"
    "• *mes* o *resumen* → el mes actual\n"
    "• *panel* → link para ver todo en tu navegador\n"
    "• *salir* → cierra el panel en todos tus dispositivos\n"
    "• *ayuda* → este mensaje"
)
ENLACE_PANEL = (
    "🖥️ Tu enlace para entrar al panel:\n{url}\n\n"
    "⏱️ Vence en {minutos} minutos y sirve una sola vez.\n"
    "🔒 No lo reenvíes: quien lo abra entra a tus finanzas."
)
SESIONES_CERRADAS = (
    "🔒 Listo, cerré tu panel en todos tus dispositivos.\n"
    "Escribe *panel* cuando quieras volver a entrar."
)
NO_ES_MOVIMIENTO = (
    "🤔 No encontré un gasto ni un ingreso en tu mensaje.\n"
    "Prueba con algo como _gasté 10 en taxi_, o escribe *ayuda*."
)
OTRA_MONEDA = "💱 Por ahora solo anoto montos en soles. Escríbemelo en soles, porfa."
DEMASIADOS = "😅 Son muchos de golpe. Mándame máximo 5 por mensaje."
NO_ENTENDI_TEXTO = "😕 No te entendí bien. Prueba con algo como _gasté 10 en taxi_."

# Palabra normalizada -> período del resumen (None = mostrar ayuda)
COMANDOS = {
    "hoy": "hoy",
    "semana": "semana",
    "mes": "mes",
    "resumen": "mes",
    "ayuda": None,
    "hola": None,
    "menu": None,
}

# Prefijos de los ids que viajan en listas y botones. Formato:
#   "cat:<transaccion_id>:<categoria_id>"  -> elegiste una categoría
#   "cambiar:<transaccion_id>"             -> quieres cambiar la categoría
#   "deshacer:<transaccion_id>"            -> quieres borrar un movimiento de texto/voz
PREFIJO_CATEGORIA = "cat"
PREFIJO_CAMBIAR = "cambiar"
PREFIJO_DESHACER = "deshacer"


@dataclass
class Respuesta:
    """Qué contestar. Si trae una transacción, se le adjuntan sus botones.

    Separar "qué responder" de "cómo enviarlo" deja la lógica testeable sin
    pensar en el formato JSON de Meta.
    """

    texto: str
    transaccion: Transaccion | None = None
    elegir_categoria: bool = False  # True = mostrar la lista aunque ya tenga categoría


# --------------------------------------------------------------------------- imágenes

def _atender_imagen(mensaje: dict, usuario: Usuario) -> Respuesta:
    try:
        datos = descargar_media(mensaje["image"]["id"])
    except MediaDemasiadoGrande:
        return Respuesta("😅 Esa imagen es muy pesada. Mándame una captura normal de Yape.")

    media_type = detectar_media_type(datos)
    if media_type is None:
        return Respuesta(NO_PUDE_LEER)

    try:
        comprobante, uso = extraer(datos, media_type)
    except ValidationError:
        # La IA respondió algo que no cumple el esquema: no guardamos datos a medias
        logger.warning("Extracción inválida en %s", mensaje.get("id"), exc_info=True)
        return Respuesta(NO_PUDE_LEER)
    except anthropic.APIError:
        logger.exception("Falla de la API de Anthropic en %s", mensaje.get("id"))
        return Respuesta(FALLA_IA)

    logger.info("Extracción: %s | tokens %s/%s",
                comprobante.tipo, uso.input_tokens, uso.output_tokens)

    if comprobante.tipo == "no_es_comprobante":
        return Respuesta(NO_ES_YAPE)

    transaccion, creada = registrar_comprobante(usuario, comprobante, mensaje.get("id", ""))
    texto = formatear_transaccion(transaccion)
    if not creada:
        texto = f"👍 Ese Yape ya lo tenías anotado:\n\n{texto}"
    return Respuesta(texto, transaccion=transaccion)


# --------------------------------------------------------------------------- texto

def normalizar_comando(texto: str) -> str:
    """'  ¡Resúmen! ' -> 'resumen'. Minúsculas, sin tildes, sin signos.

    NFD separa cada letra de su tilde ('ú' -> 'u' + '´'); luego descartamos
    las marcas (categoría Unicode 'Mn'). Así no hay que listar cada variante.
    """
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return sin_tildes.strip(string.whitespace + string.punctuation + "¡¿").lower()


def _momento_del_mensaje(mensaje: dict) -> datetime:
    """Cuándo se ENVIÓ el mensaje (Meta manda 'timestamp' en segundos Unix).

    Mejor que timezone.now(): si el worker estuvo caído y procesa el mensaje
    una hora tarde, el gasto igual queda con la hora en que lo escribiste.
    """
    try:
        return datetime.fromtimestamp(int(mensaje["timestamp"]), tz=LIMA)
    except (KeyError, ValueError, TypeError):
        return timezone.localtime(timezone.now(), LIMA)


def _atender_texto(mensaje: dict, usuario: Usuario) -> list[Respuesta]:
    texto = mensaje["text"]["body"]

    # 1) Comandos: palabras fijas, sin IA (gratis e instantáneo)
    comando = normalizar_comando(texto)
    if comando == "panel":
        logger.info("Enlace al panel pedido")  # nunca loguear la URL: lleva el token
        return [Respuesta(ENLACE_PANEL.format(
            url=crear_enlace(usuario), minutos=settings.PANEL_ENLACE_MINUTOS))]
    if comando == "salir":
        cerrar_sesiones(usuario)
        logger.info("Sesiones del panel cerradas")
        return [Respuesta(SESIONES_CERRADAS)]
    if comando in COMANDOS:
        periodo = COMANDOS[comando]
        if periodo is None:
            return [Respuesta(AYUDA)]
        logger.info("Resumen pedido: %s", periodo)
        return [Respuesta(formatear_resumen(calcular_resumen(usuario, periodo)))]

    # 2) Todo lo demás: la IA busca gastos/ingresos
    momento = _momento_del_mensaje(mensaje)
    gasto, ingreso = (
        [c.nombre for c in categorias_disponibles(usuario, tipo)]
        for tipo in (Transaccion.Tipo.GASTO, Transaccion.Tipo.INGRESO)
    )
    try:
        interpretacion, uso = interpretar(texto, gasto, ingreso, DIAS[momento.weekday()])
    except ValidationError:
        logger.warning("Interpretación inválida en %s", mensaje.get("id"), exc_info=True)
        return [Respuesta(NO_ENTENDI_TEXTO)]
    except anthropic.APIError:
        logger.exception("Falla de la API de Anthropic en %s", mensaje.get("id"))
        return [Respuesta(FALLA_IA)]

    logger.info("Interpretación: %s (%d) | tokens %s/%s", interpretacion.clase,
                len(interpretacion.movimientos), uso.input_tokens, uso.output_tokens)

    if interpretacion.clase == "no_es_movimiento":
        return [Respuesta(NO_ES_MOVIMIENTO)]
    if interpretacion.clase == "otra_moneda":
        return [Respuesta(OTRA_MONEDA)]
    if interpretacion.clase == "demasiados":
        return [Respuesta(DEMASIADOS)]

    creadas = registrar_movimientos_texto(usuario, interpretacion, momento, mensaje.get("id", ""))
    # Un mensaje por movimiento: cada uno necesita SUS botones (cambiar/deshacer)
    return [Respuesta(formatear_transaccion(t), transaccion=t) for t in creadas]


# --------------------------------------------------------------------------- botones

def _atender_interactivo(mensaje: dict, usuario: Usuario) -> Respuesta:
    """El usuario tocó una opción de una lista o un botón que le mandamos."""
    interactivo = mensaje.get("interactive", {})
    elegido = interactivo.get("list_reply") or interactivo.get("button_reply") or {}
    partes = elegido.get("id", "").split(":")

    try:
        if partes[0] == PREFIJO_CATEGORIA and len(partes) == 3:
            t = asignar_categoria(usuario, int(partes[1]), int(partes[2]))
            logger.info("Categoría asignada: tx=%s → %s%s", t.pk, t.categoria.nombre,
                        " (regla actualizada)" if t.contraparte else "")
            if t.contraparte:
                return Respuesta(
                    f"{t.categoria} ✔️ Anotado.\n"
                    f"Los próximos Yapes a {t.contraparte} irán solos a {t.categoria.nombre}."
                )
            return Respuesta(f"{t.categoria} ✔️ Listo, {t.descripcion} quedó en {t.categoria.nombre}.")

        if partes[0] == PREFIJO_CAMBIAR and len(partes) == 2:
            t = Transaccion.objects.get(
                pk=int(partes[1]), usuario=usuario, tipo=Transaccion.Tipo.GASTO
            )  # mismo cuidado que en asignar_categoria: filtrar por usuario
            return Respuesta(formatear_transaccion(t), transaccion=t, elegir_categoria=True)

        if partes[0] == PREFIJO_DESHACER and len(partes) == 2:
            t = deshacer_transaccion(usuario, int(partes[1]))
            logger.info("Transacción deshecha: tx=%s", partes[1])
            quien = t.descripcion or t.contraparte
            return Respuesta(f"🗑️ Listo, borré: {soles(t.monto)} · {quien}")
    except (ValueError, OpcionInvalida, Transaccion.DoesNotExist):
        # ValueError: int() de algo que no es número. Nunca confiamos en el id.
        logger.warning("Opción interactiva inválida: %r", elegido.get("id"))
        return Respuesta(OPCION_INVALIDA)

    logger.warning("Opción interactiva desconocida: %r", elegido.get("id"))
    return Respuesta(OPCION_INVALIDA)


# --------------------------------------------------------------------------- envío

def _armar_respuestas(mensaje: dict, usuario: Usuario) -> list[Respuesta]:
    tipo = mensaje.get("type")
    if tipo == "image":
        return [_atender_imagen(mensaje, usuario)]
    if tipo == "interactive":
        return [_atender_interactivo(mensaje, usuario)]
    if tipo == "text":
        return _atender_texto(mensaje, usuario)
    return [Respuesta(f"Todavía no entiendo mensajes de tipo '{tipo}'.")]


def _enviar_respuesta(destinatario: str, r: Respuesta, usuario: Usuario) -> None:
    t = r.transaccion
    if t is None:
        enviar_texto(destinatario, r.texto)
        return

    es_gasto = t.tipo == Transaccion.Tipo.GASTO
    if es_gasto and (t.categoria is None or r.elegir_categoria):
        # Sin categoría todavía (o pidió cambiarla): le adjuntamos la lista
        pregunta = ("¿A qué categoría lo cambio?" if r.elegir_categoria
                    else "¿En qué categoría lo pongo?")
        enviar_lista(
            destinatario,
            f"{r.texto}\n\n{pregunta}",
            "Elegir categoría",
            [(f"{PREFIJO_CATEGORIA}:{t.pk}:{c.pk}", str(c))
             for c in categorias_disponibles(usuario)],
        )
        return

    botones = []
    if es_gasto:
        botones.append((f"{PREFIJO_CAMBIAR}:{t.pk}", "Cambiar categoría"))
    if t.fuente != Transaccion.Fuente.YAPE:  # los Yapes no se deshacen desde el chat
        botones.append((f"{PREFIJO_DESHACER}:{t.pk}", "Deshacer"))

    if botones:
        enviar_botones(destinatario, r.texto, botones)
    else:
        enviar_texto(destinatario, r.texto)  # ej.: ingreso de Yape


def atender_mensaje(mensaje: dict, nombre_perfil: str = "") -> None:
    """Punto de entrada de la tarea. Recibe el mensaje tal como lo mandó Meta."""
    logger.info("Atendiendo %s (%s)", mensaje.get("id"), mensaje.get("type"))
    usuario = obtener_usuario(mensaje["from"], nombre_perfil)
    for respuesta in _armar_respuestas(mensaje, usuario):
        _enviar_respuesta(mensaje["from"], respuesta, usuario)
