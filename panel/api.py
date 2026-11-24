"""API JSON del panel. La consume la app de React (fase 3).

Reglas de esta capa:
  * Toda consulta filtra por request.usuario_panel. Los ids llegan del
    navegador: nunca hacemos get(pk=id) sin el usuario.
  * Los montos viajan como TEXTO ("18.50"), no como número: en JavaScript
    0.1 + 0.2 = 0.30000000000000004. React los muestra tal cual; si alguna vez
    necesita sumar, que lo haga en céntimos enteros.
  * Las fechas viajan en ISO 8601 con hora de Lima ("2026-11-20T09:42:00-05:00").
  * La lógica de negocio vive en finanzas/; aquí solo se lee la petición,
    se llama al servicio y se arma el JSON.
"""
import json
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Count, DateField, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from finanzas.models import Categoria, Transaccion
from finanzas.resumenes import (
    MESES,
    PERIODOS_PANEL,
    inicio_del_dia,
    rango,
    rango_comparable,
)
from finanzas.servicios import (
    CAMPOS_EDITABLES,
    LIMA,
    DatosInvalidos,
    OpcionInvalida,
    asignar_categoria,
    crear_movimiento_panel,
    editar_movimiento_panel,
    eliminar_transaccion,
)

from .sesion import api_requerida

POR_PAGINA = 20
CERO = Decimal("0")
MESES_CORTOS = [m[:3] for m in MESES]


# --------------------------------------------------------------------------- utilidades

def _dinero(valor) -> str:
    return f"{(valor or CERO):.2f}"


def _error(codigo: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": codigo}, status=status)


def _hoy() -> date:
    """Fecha de hoy en Lima. Función aparte para que los tests la puedan fijar."""
    return timezone.localtime(timezone.now(), LIMA).date()


def _periodo(request) -> str | None:
    periodo = request.GET.get("periodo", "mes")
    return periodo if periodo in PERIODOS_PANEL else None


def _referencia(request, periodo: str, hoy: date) -> date | None:
    """El día desde el que se calcula el período: hoy, o el que eligieron con ?fecha=.

    Devuelve None si `fecha` falta, está mal escrita o es futura (no hay nada que ver).
    """
    if periodo != "dia":
        return hoy
    try:
        dia = date.fromisoformat(request.GET.get("fecha", ""))
    except ValueError:
        return None
    return dia if dia <= hoy else None


def _totales(qs) -> dict:
    t = qs.aggregate(
        gastos=Sum("monto", filter=Q(tipo=Transaccion.Tipo.GASTO)),
        ingresos=Sum("monto", filter=Q(tipo=Transaccion.Tipo.INGRESO)),
        cantidad=Count("id"),
    )
    gastos, ingresos = t["gastos"] or CERO, t["ingresos"] or CERO  # Sum de nada es None
    return {"gastos": gastos, "ingresos": ingresos, "cantidad": t["cantidad"]}


def _categoria(c: Categoria | None) -> dict | None:
    if c is None:
        return None
    return {"id": c.pk, "nombre": c.nombre, "emoji": c.emoji, "tipo": c.tipo}


def _movimiento(t: Transaccion) -> dict:
    return {
        "id": t.pk,
        "tipo": t.tipo,
        "monto": _dinero(t.monto),
        "fecha_hora": timezone.localtime(t.fecha_hora, LIMA).isoformat(),
        "fuente": t.fuente,
        "contraparte": t.contraparte,
        "descripcion": t.descripcion,
        "categoria": _categoria(t.categoria),
    }


# --------------------------------------------------------------------------- resumen

def _clave_categoria(categoria_id) -> str:
    """Clave de una categoría en JSON (las claves de un objeto son texto): "7" o "sin"."""
    return "sin" if categoria_id is None else str(categoria_id)


def _sumas_por_tramo(qs, tramo) -> tuple[dict, dict, dict]:
    """Una sola consulta: total por (tramo, tipo, categoría). Python solo los reparte.

    Devuelve (gastos por tramo, ingresos por tramo, ingresos por tramo y categoría).
    Los ingresos van por categoría para poder apilar Sueldo e InDrive en la barra.
    """
    gastos, ingresos, por_categoria = {}, {}, {}
    filas = (qs.annotate(tramo=tramo).values("tramo", "tipo", "categoria_id")
             .annotate(total=Sum("monto")))
    for f in filas:
        t = f["tramo"]
        if f["tipo"] == Transaccion.Tipo.GASTO:
            gastos[t] = gastos.get(t, CERO) + f["total"]
        else:
            ingresos[t] = ingresos.get(t, CERO) + f["total"]
            por_categoria.setdefault(t, {})[_clave_categoria(f["categoria_id"])] = _dinero(f["total"])
    return gastos, ingresos, por_categoria


def _serie(usuario, periodo: str, hoy: date, inicio, fin) -> list[dict]:
    """Datos del gráfico de barras: gastos e ingresos de cada tramo.

    Año -> 12 barras (meses). Cualquier otro período -> los días del mes que lo
    contiene, marcando cuáles caen dentro del período (para resaltarlos) y
    cuáles todavía no llegan (para dibujarlos tenues).
    """
    movimientos = Transaccion.objects.filter(usuario=usuario)

    def punto(clave, sumas, **extra):
        gastos, ingresos, por_categoria = sumas
        return {
            **extra,
            "gastos": _dinero(gastos.get(clave)),
            "ingresos": _dinero(ingresos.get(clave)),
            "ingresos_por_categoria": por_categoria.get(clave, {}),
        }

    if periodo == "anio":
        # output_field=DateField: que devuelva date (1 del mes) y no datetime, para buscar por date
        sumas = _sumas_por_tramo(movimientos.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin),
                                 TruncMonth("fecha_hora", tzinfo=LIMA, output_field=DateField()))
        return [punto(
            date(hoy.year, m, 1), sumas,
            etiqueta=MESES_CORTOS[m - 1],
            fecha=date(hoy.year, m, 1).isoformat(),
            en_periodo=True,
            futuro=m > hoy.month,
        ) for m in range(1, 13)]

    mes = timezone.localtime(inicio, LIMA).date().replace(day=1)
    if periodo == "semana":
        mes = hoy.replace(day=1)  # una semana que cruza meses: mostramos el mes de hoy
    dias_del_mes = monthrange(mes.year, mes.month)[1]
    fin_mes = mes + timedelta(days=dias_del_mes)

    # TruncDate con tzinfo=LIMA: agrupa por día de LIMA, no de UTC. Sin esto,
    # un gasto de las 8 p.m. aparecería en la barra del día siguiente.
    sumas = _sumas_por_tramo(
        movimientos.filter(fecha_hora__gte=inicio_del_dia(mes), fecha_hora__lt=inicio_del_dia(fin_mes)),
        TruncDate("fecha_hora", tzinfo=LIMA))

    desde = timezone.localtime(inicio, LIMA).date()
    hasta = timezone.localtime(fin, LIMA).date()  # excluido
    serie = []
    for n in range(dias_del_mes):
        d = mes + timedelta(days=n)
        serie.append(punto(
            d, sumas,
            etiqueta=str(d.day),
            fecha=d.isoformat(),
            en_periodo=desde <= d < hasta,
            futuro=d > hoy,
        ))
    return serie


def _categorias_de_ingreso(del_periodo, total_ingresos: Decimal) -> list[dict]:
    """Ingresos del período por categoría, con lo que sirve para un ingreso DIARIO.

    `dias`: en cuántos días distintos entró plata de esa categoría (días que
    saliste a hacer InDrive). El promedio se divide entre ESOS días, no entre
    los del mes: los días que no trabajas no deben bajarlo.
    """
    filas = (del_periodo.filter(tipo=Transaccion.Tipo.INGRESO)
             .annotate(dia=TruncDate("fecha_hora", tzinfo=LIMA))
             .values("categoria_id", "categoria__nombre", "categoria__emoji", "dia")
             .annotate(total=Sum("monto")))
    por_categoria = {}
    for f in filas:  # una fila por (categoría, día)
        c = por_categoria.setdefault(f["categoria_id"], {
            "id": f["categoria_id"],
            "nombre": f["categoria__nombre"] or "Sin categoría",
            "emoji": f["categoria__emoji"] or "",
            "total": CERO, "dias": 0, "mejor_dia": None,
        })
        c["total"] += f["total"]
        c["dias"] += 1
        if c["mejor_dia"] is None or f["total"] > c["mejor_dia"][1]:
            c["mejor_dia"] = (f["dia"], f["total"])

    resultado = []
    for c in sorted(por_categoria.values(), key=lambda c: c["total"], reverse=True):
        dia, monto = c["mejor_dia"]
        resultado.append({
            **c,
            "total": _dinero(c["total"]),
            "porcentaje": round(c["total"] / total_ingresos * 100) if total_ingresos else 0,
            "promedio_por_dia": _dinero((c["total"] / c["dias"]).quantize(Decimal("0.01"))),
            "mejor_dia": {"fecha": dia.isoformat(), "total": _dinero(monto)},
        })
    return resultado


@never_cache
@require_GET
@api_requerida
def resumen(request):
    periodo = _periodo(request)
    if periodo is None:
        return _error("periodo_invalido")

    usuario, hoy = request.usuario_panel, _hoy()
    referencia = _referencia(request, periodo, hoy)
    if referencia is None:
        return _error("fecha_invalida")
    inicio, fin, titulo = rango(periodo, referencia)
    c_inicio, c_fin, c_etiqueta = rango_comparable(periodo, referencia)

    ultimo_dia = timezone.localtime(fin, LIMA).date() - timedelta(days=1)
    # Un mes en curso se muestra hasta HOY ("del 1 al 20 de noviembre"): son 30 días
    # y casi todos aún no llegan. La semana va completa hasta el domingo, que también
    # trabajas (InDrive): ver "del 16 al 22" ayuda a saber cuánto falta para cerrarla.
    hasta = ultimo_dia if periodo == "semana" else min(ultimo_dia, hoy)

    del_periodo = Transaccion.objects.filter(usuario=usuario, fecha_hora__gte=inicio, fecha_hora__lt=fin)
    actual = _totales(del_periodo)
    anterior = _totales(Transaccion.objects.filter(
        usuario=usuario, fecha_hora__gte=c_inicio, fecha_hora__lt=c_fin))

    por_categoria = (del_periodo.filter(tipo=Transaccion.Tipo.GASTO)
                     .values("categoria_id", "categoria__nombre", "categoria__emoji")
                     .annotate(total=Sum("monto")).order_by("-total"))
    total_gastos = actual["gastos"]

    return JsonResponse({
        "periodo": periodo,
        "titulo": titulo,
        "desde": timezone.localtime(inicio, LIMA).date().isoformat(),
        "hasta": hasta.isoformat(),
        "totales": {
            "gastos": _dinero(actual["gastos"]),
            "ingresos": _dinero(actual["ingresos"]),
            "balance": _dinero(actual["ingresos"] - actual["gastos"]),
            "movimientos": actual["cantidad"],
        },
        "comparacion": {
            "etiqueta": c_etiqueta,
            "gastos": _dinero(anterior["gastos"]),
            "ingresos": _dinero(anterior["ingresos"]),
        },
        "por_categoria": [{
            "id": f["categoria_id"],  # None = "Sin categoría"
            "nombre": f["categoria__nombre"] or "Sin categoría",
            "emoji": f["categoria__emoji"] or "",
            "total": _dinero(f["total"]),
            "porcentaje": round(f["total"] / total_gastos * 100) if total_gastos else 0,
        } for f in por_categoria],
        "por_categoria_ingresos": _categorias_de_ingreso(del_periodo, actual["ingresos"]),
        "serie": _serie(usuario, periodo, hoy, inicio, fin),
    })


# --------------------------------------------------------------------------- movimientos

def _leer_movimiento(request, requeridos: set[str] = frozenset()) -> dict:
    """Convierte el JSON del formulario a tipos de Python. Valida la FORMA, no el negocio.

    Aquí: "¿el monto es un texto que se lee como número?". En servicios.py:
    "¿es positivo, con 2 decimales como mucho?". Así la regla de negocio vive en
    un solo lugar y sirve igual si mañana el bot o un script crean movimientos.
    """
    try:
        datos = json.loads(request.body)
    except ValueError:
        raise DatosInvalidos("cuerpo")
    if not isinstance(datos, dict):
        raise DatosInvalidos("cuerpo")
    sobran_o_faltan = (set(datos) - CAMPOS_EDITABLES) | (requeridos - set(datos))
    if sobran_o_faltan:
        raise DatosInvalidos(min(sobran_o_faltan))

    cambios = {}
    for campo, valor in datos.items():
        if campo == "monto":
            # Texto obligatorio ("18.50"): un número de JSON llega a Python como float
            if not isinstance(valor, str):
                raise DatosInvalidos("monto")
            try:
                valor = Decimal(valor.strip())
            except InvalidOperation:
                raise DatosInvalidos("monto")
        elif campo == "fecha":
            try:
                valor = date.fromisoformat(valor)  # "2026-11-20"
            except (TypeError, ValueError):
                raise DatosInvalidos("fecha")
        elif campo == "categoria_id":
            # bool es subclase de int en Python: True pasaría como la categoría 1
            if valor is not None and (not isinstance(valor, int) or isinstance(valor, bool)):
                raise DatosInvalidos("categoria_id")
        cambios[campo] = valor
    return cambios


def _respuesta_movimiento(guardar, status: int = 200) -> JsonResponse:
    """Corre `guardar()` y traduce las excepciones del servicio a HTTP."""
    try:
        t = guardar()
    except DatosInvalidos as e:
        return JsonResponse({"error": "datos_invalidos", "campo": e.campo}, status=400)
    except OpcionInvalida:
        # 404 si la categoría o el movimiento no existen o son de otra persona
        return _error("no_encontrado", status=404)
    return JsonResponse({"movimiento": _movimiento(t)}, status=status)


def _crear_movimiento(request) -> JsonResponse:
    def guardar():
        datos = _leer_movimiento(request, requeridos={"tipo", "monto", "fecha"})
        return crear_movimiento_panel(request.usuario_panel, **datos)

    return _respuesta_movimiento(guardar, status=201)  # 201 Created


@never_cache
@require_http_methods(["GET", "POST"])
@api_requerida
def movimientos(request):
    """GET: lista filtrada y paginada. POST: crea un movimiento desde el formulario."""
    if request.method == "POST":
        return _crear_movimiento(request)

    periodo = _periodo(request)
    if periodo is None:
        return _error("periodo_invalido")

    referencia = _referencia(request, periodo, _hoy())
    if referencia is None:
        return _error("fecha_invalida")
    inicio, fin, _ = rango(periodo, referencia)
    qs = (Transaccion.objects
          .filter(usuario=request.usuario_panel, fecha_hora__gte=inicio, fecha_hora__lt=fin)
          .select_related("categoria")  # evita una consulta extra POR fila (problema N+1)
          .order_by("-fecha_hora", "-id"))

    tipo = request.GET.get("tipo")
    if tipo:
        if tipo not in Transaccion.Tipo.values:
            return _error("tipo_invalido")
        qs = qs.filter(tipo=tipo)

    categoria = request.GET.get("categoria")
    if categoria == "sin":
        qs = qs.filter(tipo=Transaccion.Tipo.GASTO, categoria__isnull=True)
    elif categoria:
        if not categoria.isdigit():
            return _error("categoria_invalida")
        qs = qs.filter(categoria_id=int(categoria))

    q = request.GET.get("q", "").strip()[:50]
    if q:
        qs = qs.filter(Q(contraparte__icontains=q) | Q(descripcion__icontains=q))

    # get_page tolera páginas raras ("abc", -1, 999): devuelve la primera o la última
    pagina = Paginator(qs, POR_PAGINA).get_page(request.GET.get("pagina"))
    return JsonResponse({
        "resultados": [_movimiento(t) for t in pagina],
        "pagina": pagina.number,
        "paginas": pagina.paginator.num_pages,
        "total": pagina.paginator.count,
    })


@require_http_methods(["PATCH", "DELETE"])
@api_requerida
def movimiento(request, transaccion_id):
    """PATCH: edita solo los campos que vienen. DELETE: borra."""
    if request.method == "PATCH":
        return _respuesta_movimiento(lambda: editar_movimiento_panel(
            request.usuario_panel, transaccion_id, _leer_movimiento(request)))

    try:
        eliminar_transaccion(request.usuario_panel, transaccion_id)
    except OpcionInvalida:
        # 404 tanto si no existe como si es de otra persona: no revelamos cuál de las dos
        return _error("no_encontrado", status=404)
    return HttpResponse(status=204)


@require_POST
@api_requerida
def cambiar_categoria(request, transaccion_id):
    try:
        datos = json.loads(request.body)
        categoria_id = int(datos["categoria_id"])
    except (ValueError, KeyError, TypeError):
        return _error("datos_invalidos")

    try:
        t = asignar_categoria(request.usuario_panel, transaccion_id, categoria_id)
    except OpcionInvalida:
        return _error("no_encontrado", status=404)

    return JsonResponse({
        "movimiento": _movimiento(t),
        # Para que React pueda avisar "los próximos Yapes a X irán a Y"
        "regla_actualizada": t.tipo == Transaccion.Tipo.GASTO and bool(t.contraparte),
    })


# --------------------------------------------------------------------------- categorías

@never_cache
@require_GET
@api_requerida
def categorias(request):
    # Todas (no solo 10): el límite de 10 era de las listas de WhatsApp, no del panel
    qs = Categoria.objects.filter(Q(usuario=None) | Q(usuario=request.usuario_panel))
    return JsonResponse({"categorias": [_categoria(c) for c in qs]})
