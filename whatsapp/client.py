"""Cliente mínimo para ENVIAR mensajes por la WhatsApp Cloud API."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _enviar(destinatario: str, contenido: dict) -> None:
    """Todos los tipos de mensaje comparten URL, token y manejo de errores.

    Cada función pública solo arma su `contenido` (texto, lista, botones).
    """
    url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
        f"/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    respuesta = requests.post(
        url,
        headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
        json={"messaging_product": "whatsapp", "to": destinatario, **contenido},
        timeout=10,  # sin timeout, una API lenta congela al worker indefinidamente
    )
    if not respuesta.ok:
        # Meta explica el error en el cuerpo: lo logueamos antes de lanzar la excepción
        logger.error("Error al enviar (%s): %s", respuesta.status_code, respuesta.text)
        respuesta.raise_for_status()
    logger.info("Respuesta enviada a %s", destinatario)


def enviar_texto(destinatario: str, texto: str) -> None:
    """Envía un mensaje de texto libre (solo válido dentro de la ventana de 24h)."""
    _enviar(destinatario, {"type": "text", "text": {"body": texto}})


# Límites de Meta para mensajes interactivos. Si los pasas, Meta responde 400.
MAX_FILAS_LISTA = 10
MAX_TITULO_FILA = 24
MAX_TITULO_BOTON = 20


def enviar_lista(destinatario: str, cuerpo: str, boton: str,
                 filas: list[tuple[str, str]]) -> None:
    """Mensaje con un botón que abre un menú. filas = [(id, título), ...].

    El `id` de cada fila es lo que vuelve en el webhook cuando el usuario elige:
    ahí metemos todo lo necesario para saber QUÉ eligió y PARA QUÉ.
    """
    _enviar(destinatario, {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": cuerpo},
            "action": {
                "button": boton[:MAX_TITULO_BOTON],
                "sections": [{
                    "title": "Categorías",
                    "rows": [{"id": i, "title": t[:MAX_TITULO_FILA]}
                             for i, t in filas[:MAX_FILAS_LISTA]],
                }],
            },
        },
    })


def enviar_botones(destinatario: str, cuerpo: str, botones: list[tuple[str, str]]) -> None:
    """Mensaje con hasta 3 botones de respuesta rápida. botones = [(id, título), ...]."""
    _enviar(destinatario, {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": cuerpo},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": i, "title": t[:MAX_TITULO_BOTON]}}
                for i, t in botones[:3]
            ]},
        },
    })


class MediaDemasiadoGrande(Exception):
    """El archivo supera el tamaño que estamos dispuestos a procesar."""


TAMANO_MAXIMO_MEDIA = 10 * 1024 * 1024  # 10 MB: una captura de Yape pesa ~100-500 KB


def descargar_media(media_id: str) -> bytes:
    """Descarga un archivo (imagen, audio...) que el usuario mandó al bot.

    El webhook NO trae la imagen, solo su media_id. Son dos pasos:
      1) Preguntar a Meta por ese media_id -> nos da una URL temporal (vence en minutos).
      2) Descargar esa URL, también con el token (sin él, Meta responde 401).
    """
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}

    # Paso 1: metadatos del archivo
    info = requests.get(
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{media_id}",
        headers=headers,
        timeout=10,
    )
    info.raise_for_status()
    datos_media = info.json()

    # Revisamos el tamaño ANTES de descargar: no bajamos 50 MB para luego descartarlos
    tamano = int(datos_media.get("file_size", 0))
    if tamano > TAMANO_MAXIMO_MEDIA:
        raise MediaDemasiadoGrande(f"{tamano} bytes")

    # Paso 2: los bytes
    archivo = requests.get(datos_media["url"], headers=headers, timeout=30)
    archivo.raise_for_status()
    logger.info("Media %s descargada (%d bytes)", media_id, len(archivo.content))
    return archivo.content
