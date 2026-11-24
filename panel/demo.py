"""Datos ficticios para la demo pública del panel (/panel/demo/).

Un usuario inventado con ~90 días de gastos e ingresos de alguien en Arequipa.
No es lógica de negocio (por eso no vive en finanzas/servicios.py): solo arma
movimientos de mentira con las mismas categorías y fuentes que los reales.

Determinismo: cada FECHA tiene su propia semilla. El 19 de noviembre genera
siempre los mismos movimientos, sin importar a qué hora corra el reset; lo
único que cambia con la hora es cuántos de HOY ya "pasaron" y se insertan.
"""
import random
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from finanzas.models import Categoria, Transaccion, Usuario
from finanzas.servicios import LIMA

# No son dígitos: nunca coincide con un "from" de Meta (que siempre lo es), y el
# webhook además solo acepta WHATSAPP_NUMEROS_PERMITIDOS.
TELEFONO_DEMO = "demo-publico"
SEMILLA = "bot-finanzas-demo"
DIAS_DE_HISTORIA = 90

# Yape enmascara los nombres: "Rosa Q. Mam*". Todos inventados.
MENU = ("Rosa Q. Mam*", "152")
FAMILIA = [("Elena S. Huam*", "418"), ("Jorge S. Huam*", "903")]
AMIGOS = [("Luis M. Cha*", "277"), ("Andrea P. Vil*", "640"), ("Kevin R. Tac*", "385"),
          ("Milagros C. Apa*", "019")]

TAMBO = ["Tambo: gaseosa y galletas", "Tambo: agua y sánguche", "Tambo: café", "Tambo: snacks"]
SALIDAS = ["Picantería: adobo arequipeño", "Cine con amigos", "Chicharronería", "Salida con amigos",
           "Pizza el fin de semana"]
FARMACIA = ["Farmacia: pastillas para la gripe", "Farmacia: vitaminas", "Farmacia"]
# (día del mes, descripción, mínimo, máximo) en céntimos
SERVICIOS = [(5, "Internet", 8900, 8900), (8, "Recibo de luz SEAL", 7000, 11000),
             (12, "Recibo de agua Sedapar", 3500, 5500), (20, "Plan del celular", 3500, 3500)]
SUELDO_QUINCENA = Decimal("1400.00")


def usuario_demo() -> Usuario:
    """El usuario de la demo, con el nombre de PANEL_DEMO_NOMBRE (lo crea si no existe)."""
    usuario, _ = Usuario.objects.get_or_create(
        telefono_wa=TELEFONO_DEMO, defaults={"nombre": settings.PANEL_DEMO_NOMBRE}
    )
    if usuario.nombre != settings.PANEL_DEMO_NOMBRE:  # cambiaron la variable: lo seguimos
        usuario.nombre = settings.PANEL_DEMO_NOMBRE
        usuario.save(update_fields=["nombre"])
    return usuario


def _soles(rng: random.Random, minimo: int, maximo: int, paso: int = 50) -> Decimal:
    """Monto al azar entre dos montos en CÉNTIMOS, en pasos de 50 céntimos. Nunca float."""
    return (Decimal(rng.randrange(minimo, maximo + 1, paso)) / 100).quantize(Decimal("0.01"))


def _hora(rng: random.Random, desde: int, hasta: int) -> time:
    """Una hora entre `desde`:00 y `hasta`:59."""
    return time(rng.randint(desde, hasta), rng.randrange(0, 60, 5))


def _movimientos_del_dia(fecha: date) -> list[dict]:
    """Todo lo que "pasó" ese día, con su hora. No sabe nada de "ahora"."""
    rng = random.Random(f"{SEMILLA}-{fecha.isoformat()}")  # semilla POR FECHA
    dia_semana = fecha.weekday()  # lunes=0 ... domingo=6
    fin_de_semana = dia_semana >= 5
    movs = []

    def gasto(categoria, monto, hora, descripcion="", yape=None):
        movs.append({"tipo": "gasto", "categoria": categoria, "monto": monto, "hora": hora,
                     "descripcion": descripcion, "yape": yape})

    def ingreso(categoria, monto, hora, descripcion="", yape=None):
        movs.append({"tipo": "ingreso", "categoria": categoria, "monto": monto, "hora": hora,
                     "descripcion": descripcion, "yape": yape})

    if not fin_de_semana:
        # Menú de mediodía: a veces por Yape a la señora del menú, a veces en efectivo
        yape = MENU if rng.random() < 0.6 else None
        gasto("Comida", _soles(rng, 1000, 1500), _hora(rng, 12, 13), "" if yape else "Menú", yape)
    if dia_semana <= 5:  # pasajes de combi de lunes a sábado
        gasto("Transporte", _soles(rng, 150, 200), _hora(rng, 7, 7), "Pasaje combi")
        gasto("Transporte", _soles(rng, 150, 200), _hora(rng, 18, 19), "Pasaje combi")
    if rng.random() < 0.35:
        gasto("Comida", _soles(rng, 300, 1800), _hora(rng, 8, 21), rng.choice(TAMBO))
    if dia_semana == 5:  # el súper de la semana
        super_ = rng.choice(["Plaza Vea", "Tottus"])
        gasto("Compras", _soles(rng, 8000, 22000, 10), _hora(rng, 10, 12), f"Súper en {super_}")
    if dia_semana in (4, 5) and rng.random() < 0.6:
        gasto("Entretenimiento", _soles(rng, 3000, 9000), _hora(rng, 20, 22), rng.choice(SALIDAS))
    if dia_semana == 6 and rng.random() < 0.5:
        gasto("Entretenimiento", _soles(rng, 2500, 6000), _hora(rng, 13, 14), rng.choice(SALIDAS))
    if rng.random() < 0.08:
        gasto("Salud", _soles(rng, 1000, 4500), _hora(rng, 9, 20), rng.choice(FARMACIA))
    if dia_semana == 6 and rng.random() < 0.3:
        gasto("Familia", _soles(rng, 2000, 10000, 1000), _hora(rng, 10, 18), "", rng.choice(FAMILIA))
    if rng.random() < 0.1:
        gasto("Otros", _soles(rng, 500, 2500), _hora(rng, 10, 21), "", rng.choice(AMIGOS))
    if fecha.day == 1:
        gasto("Hogar", Decimal("550.00"), time(10, 0), "Alquiler del cuarto")
    for dia, descripcion, minimo, maximo in SERVICIOS:
        if fecha.day == dia:
            gasto("Servicios", _soles(rng, minimo, maximo, 10), _hora(rng, 9, 19), descripcion)

    # Ingresos: sueldo el 15 y el último día del mes, InDrive algunas noches, algún Yape
    if fecha.day in (15, monthrange(fecha.year, fecha.month)[1]):
        ingreso("Sueldo", SUELDO_QUINCENA, time(9, 0), "Sueldo quincena")
    if dia_semana in (1, 3, 5) and rng.random() < 0.75:
        ingreso("InDrive", _soles(rng, 3500, 7000), _hora(rng, 21, 22), "Carreras de InDrive")
    if rng.random() < 0.07:
        ingreso("Otros ingresos", _soles(rng, 2000, 8000, 500), _hora(rng, 10, 20), "",
                rng.choice(AMIGOS))
    return movs


def generar_movimientos(usuario: Usuario, ahora: datetime | None = None) -> list[Transaccion]:
    """Los movimientos de los últimos 90 días que ya ocurrieron respecto de `ahora`.

    Devuelve objetos SIN guardar (para un bulk_create). `ahora` es inyectable en tests.
    """
    ahora = timezone.localtime(ahora or timezone.now(), LIMA)
    hoy = ahora.date()
    categorias = {c.nombre: c for c in Categoria.objects.filter(usuario=None)}

    transacciones = []
    for atras in range(DIAS_DE_HISTORIA - 1, -1, -1):
        fecha = hoy - timedelta(days=atras)
        for i, m in enumerate(_movimientos_del_dia(fecha)):
            cuando = datetime.combine(fecha, m["hora"], tzinfo=LIMA)
            if cuando > ahora:
                continue  # aún no "pasa": lo insertará un reset más tarde
            if m["categoria"] not in categorias:
                raise LookupError(f"Falta la categoría del sistema {m['categoria']!r}: ¿corriste migrate?")
            contraparte, celular3 = m["yape"] or ("", "")
            transacciones.append(Transaccion(
                usuario=usuario,
                tipo=m["tipo"],
                monto=m["monto"],
                fecha_hora=cuando,
                contraparte=contraparte,
                contraparte_celular3=celular3,
                descripcion=m["descripcion"],
                categoria=categorias[m["categoria"]],
                fuente=Transaccion.Fuente.YAPE if m["yape"] else Transaccion.Fuente.TEXTO,
                # Fijo por fecha + posición: el mismo Yape tiene el mismo número en cada reset
                numero_operacion=f"{fecha:%Y%m%d}{i:03d}" if m["yape"] else None,
            ))
    return transacciones


def regenerar(reset: bool = True) -> tuple[int, int] | None:
    """Borra SOLO los movimientos del usuario demo y los vuelve a generar.

    Devuelve (creados, borrados), o None si ya tenía datos y reset=False.
    La usan el comando seed_demo y la tarea programada de panel/tareas.py.
    """
    demo = usuario_demo()
    existentes = Transaccion.objects.filter(usuario=demo)
    if not reset and existentes.exists():
        return None
    nuevos = generar_movimientos(demo)  # antes del atomic: si falla, no se borra nada
    # Todo o nada: quien mire la demo justo ahora ve los datos viejos o los nuevos,
    # nunca una demo vacía a medio regenerar.
    with transaction.atomic():
        borrados, _ = existentes.delete()
        Transaccion.objects.bulk_create(nuevos)
    return len(nuevos), borrados
