"""Resúmenes de gastos e ingresos por período (hoy, semana, mes).

Dos reglas guían este módulo:
  1. Las fechas se calculan en hora de LIMA. "Hoy" empieza a las 00:00 de Lima,
     no de UTC; si no, un Yape de las 8 p.m. caería en el resumen de mañana.
  2. La base de datos suma y agrupa (GROUP BY). Python solo da formato.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import Transaccion, Usuario
from .servicios import LIMA, soles

PERIODOS = ("hoy", "semana", "mes")  # los que entiende el bot
PERIODOS_PANEL = PERIODOS + ("mes_pasado", "anio", "dia")  # el panel ofrece tres más
# "dia" = un día cualquiera que eliges en el panel. Para "dia", el parámetro `hoy`
# de rango() y rango_comparable() es ESE día: un día pasado se calcula igual que hoy.
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
SIN_CATEGORIA = "❓ Sin categoría"


@dataclass
class Resumen:
    titulo: str
    gastos: list[tuple[str, Decimal]] = field(default_factory=list)  # (categoría, total)
    total_gastos: Decimal = Decimal("0")
    total_ingresos: Decimal = Decimal("0")
    movimientos: int = 0


def rango(periodo: str, hoy: date) -> tuple[datetime, datetime, str]:
    """Devuelve (inicio, fin, título). El rango es [inicio, fin): incluye inicio, excluye fin.

    Usar "menor que el inicio del día siguiente" en vez de "menor o igual a las
    23:59:59" evita perder un Yape hecho a las 23:59:59.5.
    """
    if periodo == "hoy":
        desde, hasta = hoy, hoy + timedelta(days=1)
        titulo = f"Hoy, {DIAS[hoy.weekday()]} {hoy:%d/%m}"
    elif periodo == "dia":
        desde, hasta = hoy, hoy + timedelta(days=1)
        titulo = f"{DIAS[hoy.weekday()].capitalize()} {hoy.day} de {MESES[hoy.month - 1]}"
    elif periodo == "semana":
        desde = hoy - timedelta(days=hoy.weekday())  # weekday(): lunes=0
        hasta = desde + timedelta(days=7)
        titulo = f"Esta semana (lun {desde:%d/%m} – hoy)"
    elif periodo == "mes":
        desde = hoy.replace(day=1)
        hasta = (desde + timedelta(days=32)).replace(day=1)  # truco: día 1 del mes siguiente
        titulo = f"{MESES[hoy.month - 1].capitalize()} {hoy.year}"
    elif periodo == "mes_pasado":
        hasta = hoy.replace(day=1)
        desde = _inicio_mes_anterior(hasta)
        titulo = f"{MESES[desde.month - 1].capitalize()} {desde.year}"
    elif periodo == "anio":
        desde, hasta = date(hoy.year, 1, 1), date(hoy.year + 1, 1, 1)
        titulo = str(hoy.year)
    else:
        raise ValueError(f"Período desconocido: {periodo}")

    return inicio_del_dia(desde), inicio_del_dia(hasta), titulo


def inicio_del_dia(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=LIMA)


def _inicio_mes_anterior(inicio_de_mes: date) -> date:
    return (inicio_de_mes - timedelta(days=1)).replace(day=1)


def rango_comparable(periodo: str, hoy: date) -> tuple[datetime, datetime, str]:
    """El tramo EQUIVALENTE del período anterior, para el "% vs. antes".

    Comparar el 1–20 de noviembre contra octubre COMPLETO siempre haría parecer
    que gastaste menos (20 días contra 31). Por eso, para un período en curso,
    comparamos contra la misma cantidad de días del período anterior.
    """
    if periodo == "hoy":
        ayer = hoy - timedelta(days=1)
        return inicio_del_dia(ayer), inicio_del_dia(hoy), "ayer"
    if periodo == "dia":
        antes = hoy - timedelta(days=1)
        return inicio_del_dia(antes), inicio_del_dia(hoy), f"el {DIAS[antes.weekday()]} {antes.day}"
    if periodo == "semana":
        lunes_pasado = hoy - timedelta(days=hoy.weekday() + 7)
        fin = lunes_pasado + timedelta(days=hoy.weekday() + 1)
        return inicio_del_dia(lunes_pasado), inicio_del_dia(fin), "el mismo tramo de la semana pasada"
    if periodo == "mes":
        este_mes = hoy.replace(day=1)
        desde = _inicio_mes_anterior(este_mes)
        # min(): el 31/03 se compara con el 1–28/02, no se pasa a marzo
        hasta = min(desde + timedelta(days=hoy.day), este_mes)
        ultimo = hasta - timedelta(days=1)
        return (inicio_del_dia(desde), inicio_del_dia(hasta),
                f"el 1–{ultimo.day} de {MESES[desde.month - 1]}")
    if periodo == "mes_pasado":
        desde = _inicio_mes_anterior(hoy.replace(day=1))
        anterior = _inicio_mes_anterior(desde)
        return inicio_del_dia(anterior), inicio_del_dia(desde), MESES[anterior.month - 1]
    if periodo == "anio":
        try:
            mismo_dia = hoy.replace(year=hoy.year - 1)
        except ValueError:  # hoy es 29 de febrero y el año pasado no fue bisiesto
            mismo_dia = date(hoy.year - 1, 2, 28)
        return (inicio_del_dia(date(hoy.year - 1, 1, 1)),
                inicio_del_dia(mismo_dia + timedelta(days=1)),
                f"el mismo tramo de {hoy.year - 1}")
    raise ValueError(f"Período desconocido: {periodo}")


def calcular_resumen(usuario: Usuario, periodo: str, ahora: datetime | None = None) -> Resumen:
    """`ahora` es inyectable para que los tests no dependan del reloj real."""
    hoy = timezone.localtime(ahora or timezone.now(), LIMA).date()
    inicio, fin, titulo = rango(periodo, hoy)
    movimientos = Transaccion.objects.filter(
        usuario=usuario, fecha_hora__gte=inicio, fecha_hora__lt=fin
    )

    # Una sola consulta con GROUP BY categoría, ordenada de mayor a menor gasto
    por_categoria = (
        movimientos.filter(tipo=Transaccion.Tipo.GASTO)
        .values("categoria__nombre", "categoria__emoji")
        .annotate(total=Sum("monto"))
        .order_by("-total")
    )
    totales = movimientos.aggregate(
        cantidad=Count("id"),
        gastos=Sum("monto", filter=Q(tipo=Transaccion.Tipo.GASTO)),
        ingresos=Sum("monto", filter=Q(tipo=Transaccion.Tipo.INGRESO)),
    )

    return Resumen(
        titulo=titulo,
        gastos=[
            (f"{fila['categoria__emoji']} {fila['categoria__nombre']}".strip()
             if fila["categoria__nombre"] else SIN_CATEGORIA,
             fila["total"])
            for fila in por_categoria
        ],
        total_gastos=totales["gastos"] or Decimal("0"),  # Sum de nada es None, no 0
        total_ingresos=totales["ingresos"] or Decimal("0"),
        movimientos=totales["cantidad"],
    )


def formatear_resumen(r: Resumen) -> str:
    if r.movimientos == 0:
        return f"📊 {r.titulo}\n\nNo tienes movimientos registrados en este período."

    lineas = [f"📊 {r.titulo}", "", f"💸 Gastos: {soles(r.total_gastos)}"]
    for etiqueta, total in r.gastos:
        porcentaje = round(total / r.total_gastos * 100)
        lineas.append(f"   {etiqueta}: {soles(total)} ({porcentaje}%)")
    lineas.append(f"💰 Ingresos: {soles(r.total_ingresos)}")

    balance = r.total_ingresos - r.total_gastos
    signo = "+" if balance >= 0 else "-"
    lineas += ["", f"Balance: {signo}{soles(abs(balance))}"]
    return "\n".join(lineas)
