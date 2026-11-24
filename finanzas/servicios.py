"""Operaciones de negocio sobre las finanzas del usuario.

Aquí vive el "cómo se guarda un gasto". Las tareas del bot llaman a estas
funciones; ni WhatsApp ni la IA saben nada de la base de datos.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from comprobantes.schemas import ComprobanteYape, InterpretacionTexto

from .models import Categoria, ReglaCategoria, Transaccion, Usuario

LIMA = ZoneInfo("America/Lima")


def obtener_usuario(telefono_wa: str, nombre: str = "") -> Usuario:
    """Devuelve el usuario de ese número, creándolo la primera vez que escribe."""
    usuario, creado = Usuario.objects.get_or_create(
        telefono_wa=telefono_wa, defaults={"nombre": nombre}
    )
    if not creado and nombre and not usuario.nombre:
        usuario.nombre = nombre
        usuario.save(update_fields=["nombre"])
    return usuario


def registrar_comprobante(
    usuario: Usuario, comprobante: ComprobanteYape, wamid: str = ""
) -> tuple[Transaccion, bool]:
    """Guarda un comprobante de Yape. Devuelve (transacción, fue_creada).

    Si esa operación ya estaba registrada, la BD rechaza el INSERT por la
    restricción `transaccion_operacion_unica` y devolvemos la existente con
    fue_creada=False. El candado lo pone la BD, no un `if exists()`.
    """
    tipo = (
        Transaccion.Tipo.GASTO if comprobante.tipo == "enviado" else Transaccion.Tipo.INGRESO
    )
    # Python arma la fecha con zona horaria (lo determinista no se le delega a la IA)
    fecha_hora = datetime.combine(comprobante.fecha, comprobante.hora, tzinfo=LIMA)

    try:
        with transaction.atomic():
            nueva = Transaccion.objects.create(
                usuario=usuario,
                tipo=tipo,
                monto=comprobante.monto,
                fecha_hora=fecha_hora,
                contraparte=comprobante.contraparte or "",
                contraparte_celular3=comprobante.celular_ultimos3 or "",
                descripcion=comprobante.mensaje or "",
                fuente=Transaccion.Fuente.YAPE,
                numero_operacion=comprobante.numero_operacion,
                wamid_origen=wamid,
                categoria=_categoria_aprendida(usuario, tipo, comprobante),
            )
        return nueva, True
    except IntegrityError:
        existente = Transaccion.objects.get(
            usuario=usuario,
            fuente=Transaccion.Fuente.YAPE,
            numero_operacion=comprobante.numero_operacion,
        )
        return existente, False


def registrar_movimientos_texto(
    usuario: Usuario, interpretacion: InterpretacionTexto, momento: datetime, wamid: str = ""
) -> list[Transaccion]:
    """Guarda los gastos/ingresos que la IA entendió de un mensaje escrito.

    `momento` es cuándo se envió el mensaje (timestamp de Meta). "Ayer" se
    resuelve aquí restando días: la IA no decide fechas.

    Todo dentro de un atomic(): si un movimiento falla, no queda la mitad guardada.
    No hay dedupe por número de operación (el texto no lo tiene); los reintentos
    de Meta ya los frena MensajeProcesado por wamid.
    """
    # Clave (tipo, nombre): si la IA le pone "InDrive" a un gasto, no hay match y
    # queda sin categoría. La IA propone; Python decide qué se guarda.
    categorias = {
        (c.tipo, c.nombre): c
        for tipo in Transaccion.Tipo.values
        for c in categorias_disponibles(usuario, tipo)
    }
    creadas = []
    with transaction.atomic():
        for m in interpretacion.movimientos:
            tipo = Transaccion.Tipo.GASTO if m.tipo == "gasto" else Transaccion.Tipo.INGRESO
            creadas.append(Transaccion.objects.create(
                usuario=usuario,
                tipo=tipo,
                monto=m.monto,
                fecha_hora=momento - timedelta(days=m.dias_atras),
                descripcion=m.descripcion,
                # .get(): si la IA devolviera un nombre que no existe, queda sin categoría
                categoria=categorias.get((tipo, m.categoria)),
                fuente=Transaccion.Fuente.TEXTO,
                wamid_origen=wamid,
            ))
    return creadas


def deshacer_transaccion(usuario: Usuario, transaccion_id: int) -> Transaccion:
    """Borra un movimiento de texto o voz. Los Yapes NO: tienen comprobante real.

    Mismo cuidado que asignar_categoria: filtramos por usuario porque el id viene
    del teléfono. Devuelve la transacción borrada (en memoria) para confirmarla.
    """
    try:
        t = Transaccion.objects.select_related("categoria").get(
            pk=transaccion_id, usuario=usuario,
            fuente__in=[Transaccion.Fuente.TEXTO, Transaccion.Fuente.VOZ],
        )
    except Transaccion.DoesNotExist:
        raise OpcionInvalida(f"deshacer tx={transaccion_id}")
    t.delete()
    return t


def eliminar_transaccion(usuario: Usuario, transaccion_id: int) -> None:
    """Borra CUALQUIER movimiento del usuario, Yapes incluidos (solo desde el panel).

    A diferencia de deshacer_transaccion (chat), aquí sí se borran Yapes: sirve
    si la IA leyó mal un comprobante. Si vuelves a mandar la captura, entra de
    nuevo, porque el candado de numero_operacion ya no la encuentra.
    """
    borrados, _ = Transaccion.objects.filter(pk=transaccion_id, usuario=usuario).delete()
    if not borrados:
        raise OpcionInvalida(f"eliminar tx={transaccion_id}")


def _normalizar(contraparte: str) -> str:
    """'Juan  Per*' y 'juan per*' son la misma persona para las reglas.

    La IA puede variar mayúsculas o espacios entre una lectura y otra;
    si guardáramos el texto crudo, la regla dejaría de coincidir por un detalle.
    """
    return " ".join(contraparte.split()).casefold()


def _categoria_aprendida(usuario: Usuario, tipo: str, comprobante: ComprobanteYape):
    if tipo != Transaccion.Tipo.GASTO or not comprobante.contraparte:
        return None  # decisión: los ingresos no se categorizan (por ahora)
    regla = ReglaCategoria.objects.filter(
        usuario=usuario,
        contraparte=_normalizar(comprobante.contraparte),
        contraparte_celular3=comprobante.celular_ultimos3 or "",
    ).select_related("categoria").first()
    return regla.categoria if regla else None


def categorias_disponibles(usuario: Usuario, tipo: str = Transaccion.Tipo.GASTO) -> list[Categoria]:
    """Las del sistema + las propias del usuario, de UN tipo. WhatsApp acepta máximo 10 filas.

    Filtrar por tipo importa: sin él, "Sueldo" o "InDrive" aparecerían en la
    lista de categorías de un gasto y empujarían fuera del límite de 10 a otras.
    """
    return list(Categoria.objects.filter(Q(usuario=None) | Q(usuario=usuario), tipo=tipo)[:10])


class OpcionInvalida(Exception):
    """El id que volvió de WhatsApp no corresponde a algo que este usuario pueda tocar."""


def asignar_categoria(usuario: Usuario, transaccion_id: int, categoria_id: int) -> Transaccion:
    """Pone la categoría a un movimiento y, si es un gasto, actualiza la regla de esa contraparte.

    OJO con la seguridad: transaccion_id y categoria_id llegan desde el teléfono
    o el navegador. Por eso NUNCA hacemos Transaccion.objects.get(pk=transaccion_id)
    a secas: filtramos también por usuario, para que nadie pueda tocar
    movimientos ajenos inventándose un id.
    """
    try:
        t = Transaccion.objects.get(pk=transaccion_id, usuario=usuario)
    except Transaccion.DoesNotExist:
        raise OpcionInvalida(f"tx={transaccion_id} cat={categoria_id}")
    categoria = _categoria_para(usuario, t.tipo, categoria_id)

    with transaction.atomic():  # la transacción y su regla cambian juntas o ninguna
        t.categoria = categoria
        t.save(update_fields=["categoria"])
        _recordar_regla(usuario, t)
    return t


def _categoria_para(usuario: Usuario, tipo: str, categoria_id: int | None) -> Categoria | None:
    """La categoría pedida, solo si es del usuario (o del sistema) y del MISMO tipo.

    Una ajena, una inexistente o una de otro tipo ("InDrive" para un gasto) dan
    el mismo error: así no revelamos qué ids existen.
    """
    if categoria_id is None:
        return None
    try:
        return Categoria.objects.get(Q(usuario=None) | Q(usuario=usuario), pk=categoria_id, tipo=tipo)
    except Categoria.DoesNotExist:
        raise OpcionInvalida(f"cat={categoria_id} tipo={tipo}")


def _recordar_regla(usuario: Usuario, t: Transaccion) -> bool:
    """Si es un gasto a una contraparte (Yape), guarda la regla. Devuelve si la guardó.

    Los ingresos no aprenden reglas: la clave de la regla es la contraparte, y la
    misma persona a la que le pagas puede ser la que te paga. Una sola regla
    por contraparte no puede decir "Comida" e "InDrive" a la vez.
    """
    if t.tipo != Transaccion.Tipo.GASTO or not t.contraparte or t.categoria is None:
        return False
    # update_or_create: si ya había regla (corrección), la pisa
    ReglaCategoria.objects.update_or_create(
        usuario=usuario,
        contraparte=_normalizar(t.contraparte),
        contraparte_celular3=t.contraparte_celular3,
        defaults={"categoria": t.categoria},
    )
    return True


# --------------------------------------------------------------------------- panel

class DatosInvalidos(Exception):
    """Un dato que llegó del formulario del panel no es válido. `campo` dice cuál."""

    def __init__(self, campo: str):
        super().__init__(campo)
        self.campo = campo


MONTO_MAXIMO = Decimal("99999999.99")  # lo que cabe en max_digits=10, decimal_places=2
MAX_DESCRIPCION = Transaccion._meta.get_field("descripcion").max_length
CAMPOS_EDITABLES = {"tipo", "monto", "fecha", "categoria_id", "descripcion"}
# Monto, fecha y tipo de un Yape vienen del comprobante: son la fuente de verdad.
# Si la IA los leyó mal, se borra y se reenvía la captura.
EDITABLES_EN_YAPE = {"categoria_id", "descripcion"}


def _validar_tipo(tipo) -> str:
    if tipo not in Transaccion.Tipo.values:
        raise DatosInvalidos("tipo")
    return tipo


def _validar_monto(monto) -> Decimal:
    """Solo Decimal: si llegara un float (18.1 = 18.0999...), ya sería tarde para arreglarlo."""
    if (not isinstance(monto, Decimal) or not monto.is_finite()
            or monto <= 0 or monto > MONTO_MAXIMO
            or monto.as_tuple().exponent < -2):  # exponent -3 = tres decimales: 18.505
        raise DatosInvalidos("monto")
    return monto.quantize(Decimal("0.01"))


def _validar_descripcion(texto) -> str:
    if not isinstance(texto, str) or len(texto.strip()) > MAX_DESCRIPCION:
        raise DatosInvalidos("descripcion")
    return texto.strip()


def _ahora_lima(ahora: datetime | None) -> datetime:
    return timezone.localtime(ahora or timezone.now(), LIMA)


def _fecha_hora(fecha, hora: time, ahora: datetime) -> datetime:
    """Une la fecha elegida en el panel con una hora, sin dejar que caiga en el futuro.

    El panel solo pide la FECHA (nadie recuerda a qué hora hizo un viaje de InDrive).
    min(): si hoy eliges una hora que aún no llega, queda en "ahora".
    """
    if not isinstance(fecha, date) or isinstance(fecha, datetime) or fecha > ahora.date():
        raise DatosInvalidos("fecha")
    return min(datetime.combine(fecha, hora, tzinfo=LIMA), ahora)


def crear_movimiento_panel(
    usuario: Usuario, *, tipo: str, monto: Decimal, fecha: date,
    categoria_id: int | None = None, descripcion: str = "", ahora: datetime | None = None,
) -> Transaccion:
    """Gasto o ingreso cargado a mano desde el panel. `ahora` es inyectable para los tests.

    Hora: si es de hoy, la de este momento; si es de otro día, mediodía
    (un punto neutro que nunca cambia de fecha al pasar a UTC).
    """
    ahora = _ahora_lima(ahora)
    tipo = _validar_tipo(tipo)
    hora = ahora.time() if fecha == ahora.date() else time(12, 0)
    return Transaccion.objects.create(
        usuario=usuario,
        tipo=tipo,
        monto=_validar_monto(monto),
        fecha_hora=_fecha_hora(fecha, hora, ahora),
        categoria=_categoria_para(usuario, tipo, categoria_id),
        descripcion=_validar_descripcion(descripcion),
        fuente=Transaccion.Fuente.PANEL,
    )


def editar_movimiento_panel(
    usuario: Usuario, transaccion_id: int, cambios: dict, ahora: datetime | None = None
) -> Transaccion:
    """Aplica `cambios` (solo los campos que vienen) a un movimiento del usuario.

    En un Yape solo se puede cambiar categoría y descripción. Si el formulario
    manda el monto, la fecha o el tipo SIN cambiarlos, se acepta: así React
    puede enviar el formulario completo sin preguntarse de dónde vino el movimiento.
    """
    try:
        t = Transaccion.objects.select_related("categoria").get(pk=transaccion_id, usuario=usuario)
    except Transaccion.DoesNotExist:
        raise OpcionInvalida(f"editar tx={transaccion_id}")
    desconocidos = set(cambios) - CAMPOS_EDITABLES
    if desconocidos:
        raise DatosInvalidos(min(desconocidos))

    ahora = _ahora_lima(ahora)
    local = timezone.localtime(t.fecha_hora, LIMA)
    tipo = _validar_tipo(cambios.get("tipo", t.tipo))
    monto = _validar_monto(cambios["monto"]) if "monto" in cambios else t.monto
    fecha = cambios.get("fecha", local.date())

    if t.fuente == Transaccion.Fuente.YAPE:
        for campo, nuevo, actual in (("tipo", tipo, t.tipo), ("monto", monto, t.monto),
                                     ("fecha", fecha, local.date())):
            if nuevo != actual:
                raise DatosInvalidos(f"{campo}_no_editable")

    if fecha != local.date():  # cambió el día: conserva la hora que tenía
        t.fecha_hora = _fecha_hora(fecha, local.time(), ahora)
    if "categoria_id" in cambios:
        t.categoria = _categoria_para(usuario, tipo, cambios["categoria_id"])
    elif t.categoria is not None and t.categoria.tipo != tipo:
        t.categoria = None  # pasó de gasto a ingreso: "Comida" ya no le corresponde
    if "descripcion" in cambios:
        t.descripcion = _validar_descripcion(cambios["descripcion"])
    t.tipo, t.monto = tipo, monto

    with transaction.atomic():
        t.save()
        if "categoria_id" in cambios:
            _recordar_regla(usuario, t)
    return t


def soles(monto) -> str:
    """S/ 1,234.50 — separador de miles y siempre 2 decimales.

    Un solo lugar para el formato de dinero: si mañana cambia, cambia en todo el bot.
    """
    return f"S/ {monto:,.2f}"


def _hora_12h(momento: datetime) -> str:
    sufijo = "a.m." if momento.hour < 12 else "p.m."
    return f"{momento.hour % 12 or 12}:{momento:%M} {sufijo}"


def formatear_transaccion(t: Transaccion) -> str:
    local = timezone.localtime(t.fecha_hora, LIMA)
    if t.tipo == Transaccion.Tipo.GASTO:
        encabezado, flecha = "✅ Gasto anotado", "→"
    else:
        encabezado, flecha = "💰 Ingreso anotado", "←"

    if t.contraparte:  # Yape: a quién le pagaste
        lineas = [encabezado, f"{soles(t.monto)} {flecha} {t.contraparte}"]
    else:  # texto/voz: qué fue
        lineas = [encabezado, f"{soles(t.monto)} · {t.descripcion}"]
    if t.categoria:
        lineas.append(str(t.categoria))
    if t.contraparte and t.descripcion:  # el mensaje del Yape ("Pan")
        lineas.append(f"📝 {t.descripcion}")
    lineas.append(f"📅 {local:%d/%m} · {_hora_12h(local)}")
    return "\n".join(lineas)
