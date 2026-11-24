import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase

from finanzas.models import Categoria, ReglaCategoria, Transaccion, Usuario
from finanzas.servicios import LIMA

from .sesion import CLAVE_USUARIO, CLAVE_VERSION

HOY = date(2026, 11, 20)  # viernes


def _lima(y, m, d, h=12, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=LIMA)


def _iniciar_sesion(client: Client, usuario: Usuario) -> None:
    """Atajo de los tests: escribe la sesión directo (el flujo real ya se prueba en tests.py)."""
    s = client.session
    s[CLAVE_USUARIO] = usuario.pk
    s[CLAVE_VERSION] = usuario.sesion_version
    s.save()


class ApiBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.u = Usuario.objects.create(telefono_wa="51999999999", nombre="Gonzalo")
        cls.otro = Usuario.objects.create(telefono_wa="51888888888", nombre="Otro")
        cls.comida = Categoria.objects.get(nombre="Comida", usuario=None)
        cls.compras = Categoria.objects.get(nombre="Compras", usuario=None)
        n = iter(range(1, 100))

        def mov(monto, cuando, tipo="gasto", cat=None, fuente="texto", quien="", desc="", usuario=None):
            return Transaccion.objects.create(
                usuario=usuario or cls.u, tipo=tipo, monto=Decimal(monto), fecha_hora=cuando,
                categoria=cat, fuente=fuente, contraparte=quien, descripcion=desc,
                numero_operacion=str(next(n)) if fuente == "yape" else None)

        cls.ana = mov("18.50", _lima(2026, 11, 20, 9), cat=cls.comida, fuente="yape", quien="Ana G.")
        # 20:30 en Lima = 01:30 del día SIGUIENTE en UTC: prueba que agrupamos por día de Lima
        cls.taxi = mov("6.00", _lima(2026, 11, 19, 20, 30), desc="taxi")
        cls.ingreso = mov("150.00", _lima(2026, 11, 18), tipo="ingreso", fuente="yape", quien="Maria L.")
        cls.juan = mov("45.90", _lima(2026, 11, 16), cat=cls.compras, fuente="yape", quien="Juan P.")
        cls.zapas = mov("100.00", _lima(2026, 11, 3), cat=cls.compras, desc="zapatillas")
        mov("30.00", _lima(2026, 11, 13), cat=cls.comida, desc="almuerzo")      # semana pasada
        mov("70.00", _lima(2026, 10, 15), cat=cls.comida, desc="cena")          # 1–20 de octubre
        mov("999.00", _lima(2026, 10, 25), cat=cls.comida, desc="fuera del tramo")
        mov("2400.00", _lima(2025, 11, 10), tipo="ingreso", desc="sueldo 2025")
        cls.ajeno = mov("500.00", _lima(2026, 11, 20), desc="de otra persona", usuario=cls.otro)

    def setUp(self):
        # Patcher en setUp (no @patch en la clase): así también aplica a las subclases
        parche = patch("panel.api._hoy", return_value=HOY)
        parche.start()
        self.addCleanup(parche.stop)
        _iniciar_sesion(self.client, self.u)

    def _get(self, url, **params):
        r = self.client.get(url, params)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()


class ResumenApiTests(ApiBase):
    URL = "/panel/api/resumen/"

    def test_sin_sesion_responde_401_en_json(self):
        self.client.session.flush()
        r = Client().get(self.URL)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json(), {"error": "sin_sesion"})

    def test_mes_totales_y_comparacion_con_el_mismo_tramo(self):
        d = self._get(self.URL, periodo="mes")
        self.assertEqual(d["titulo"], "Noviembre 2026")
        self.assertEqual((d["desde"], d["hasta"]), ("2026-11-01", "2026-11-20"))  # hasta hoy
        self.assertEqual(d["totales"], {
            "gastos": "200.40", "ingresos": "150.00", "balance": "-50.40", "movimientos": 6,
        })  # los 500 del otro usuario no aparecen
        self.assertEqual(d["comparacion"],
                         {"etiqueta": "el 1–20 de octubre", "gastos": "70.00", "ingresos": "0.00"})

    def test_por_categoria_ordenado_con_porcentajes(self):
        d = self._get(self.URL, periodo="mes")
        self.assertEqual(
            [(c["nombre"], c["total"], c["porcentaje"]) for c in d["por_categoria"]],
            [("Compras", "145.90", 73), ("Comida", "48.50", 24), ("Sin categoría", "6.00", 3)],
        )
        self.assertIsNone(d["por_categoria"][2]["id"])

    def test_serie_del_mes_agrupa_por_dia_de_lima(self):
        serie = self._get(self.URL, periodo="mes")["serie"]
        self.assertEqual(len(serie), 30)
        por_dia = {p["etiqueta"]: p for p in serie}
        self.assertEqual(por_dia["19"]["gastos"], "6.00")  # no se fue al 20
        self.assertEqual(por_dia["20"]["gastos"], "18.50")
        self.assertFalse(por_dia["20"]["futuro"])
        self.assertTrue(por_dia["21"]["futuro"])

    def test_hoy_se_compara_con_ayer(self):
        d = self._get(self.URL, periodo="hoy")
        self.assertEqual(d["totales"]["gastos"], "18.50")
        self.assertEqual(d["comparacion"]["etiqueta"], "ayer")
        self.assertEqual(d["comparacion"]["gastos"], "6.00")

    def test_semana_resalta_solo_sus_dias(self):
        d = self._get(self.URL, periodo="semana")
        self.assertEqual((d["desde"], d["hasta"]), ("2026-11-16", "2026-11-22"))  # hasta el domingo
        self.assertEqual(d["totales"]["gastos"], "70.40")  # lun 16 a hoy
        self.assertEqual(d["comparacion"]["gastos"], "30.00")  # lun 9 al vie 13
        por_dia = {p["etiqueta"]: p for p in d["serie"]}
        self.assertFalse(por_dia["15"]["en_periodo"])
        self.assertTrue(por_dia["16"]["en_periodo"])

    def test_mes_pasado_completo(self):
        d = self._get(self.URL, periodo="mes_pasado")
        self.assertEqual(d["titulo"], "Octubre 2026")
        self.assertEqual(d["totales"]["gastos"], "1069.00")
        self.assertEqual(len(d["serie"]), 31)

    def test_anio_con_serie_por_meses(self):
        d = self._get(self.URL, periodo="anio")
        self.assertEqual(d["comparacion"]["ingresos"], "2400.00")
        self.assertEqual(len(d["serie"]), 12)
        self.assertEqual(d["serie"][10]["gastos"], "200.40")  # noviembre
        self.assertTrue(d["serie"][11]["futuro"])  # diciembre

    def test_periodo_invalido(self):
        r = self.client.get(self.URL, {"periodo": "siglo"})
        self.assertEqual(r.status_code, 400)

    def test_un_dia_pasado(self):
        d = self._get(self.URL, periodo="dia", fecha="2026-11-19")
        self.assertEqual(d["titulo"], "Jueves 19 de noviembre")
        self.assertEqual((d["desde"], d["hasta"]), ("2026-11-19", "2026-11-19"))
        # El taxi de las 20:30 (01:30 UTC del 20) es del 19 en Lima
        self.assertEqual(d["totales"]["gastos"], "6.00")
        self.assertEqual(d["comparacion"], {"etiqueta": "el miércoles 18",
                                            "gastos": "0.00", "ingresos": "150.00"})
        # La serie es la del mes del día, resaltando solo ese día
        por_dia = {p["etiqueta"]: p for p in d["serie"]}
        self.assertTrue(por_dia["19"]["en_periodo"])
        self.assertFalse(por_dia["18"]["en_periodo"])
        self.assertTrue(por_dia["21"]["futuro"])  # "futuro" sigue siendo respecto de HOY

    def test_un_dia_de_otro_mes_muestra_ese_mes(self):
        d = self._get(self.URL, periodo="dia", fecha="2026-10-15")
        self.assertEqual(d["totales"]["gastos"], "70.00")
        self.assertEqual(len(d["serie"]), 31)  # octubre
        self.assertFalse(any(p["futuro"] for p in d["serie"]))

    def test_dia_sin_fecha_mal_escrita_o_futura_da_400(self):
        for params in ({}, {"fecha": "19/11/2026"}, {"fecha": "2026-11-21"}):
            with self.subTest(params):
                r = self.client.get(self.URL, {"periodo": "dia", **params})
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.json(), {"error": "fecha_invalida"})


class IngresosEnResumenTests(ApiBase):
    """InDrive varios días + un sueldo, para el gráfico, la dona y la tarjeta."""

    URL = "/panel/api/resumen/"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.indrive = Categoria.objects.get(nombre="InDrive", usuario=None)
        cls.sueldo = Categoria.objects.get(nombre="Sueldo", usuario=None)

        def ingreso(monto, cuando, cat):
            Transaccion.objects.create(usuario=cls.u, tipo="ingreso", monto=Decimal(monto),
                                       fecha_hora=cuando, categoria=cat, fuente="panel")

        ingreso("40.00", _lima(2026, 11, 17, 21), cls.indrive)
        ingreso("20.00", _lima(2026, 11, 19, 8), cls.indrive)   # el 19, dos veces:
        ingreso("35.00", _lima(2026, 11, 19, 22), cls.indrive)  # cuenta como UN día trabajado
        ingreso("2500.00", _lima(2026, 11, 15), cls.sueldo)
        ingreso("300.00", _lima(2026, 11, 2), cls.indrive)
        Transaccion.objects.create(usuario=cls.otro, tipo="ingreso", monto=Decimal("999.00"),
                                   fecha_hora=_lima(2026, 11, 19), categoria=cls.indrive, fuente="panel")

    def test_serie_trae_ingresos_por_categoria(self):
        por_dia = {p["etiqueta"]: p for p in self._get(self.URL, periodo="mes")["serie"]}
        self.assertEqual(por_dia["19"]["ingresos"], "55.00")  # sin los 999 del otro usuario
        self.assertEqual(por_dia["19"]["ingresos_por_categoria"], {str(self.indrive.pk): "55.00"})
        self.assertEqual(por_dia["19"]["gastos"], "6.00")
        # El Yape recibido de Maria (sin categoría) va con la clave "sin"
        self.assertEqual(por_dia["18"]["ingresos_por_categoria"], {"sin": "150.00"})
        self.assertEqual(por_dia["21"]["ingresos"], "0.00")

    def test_serie_anual_tambien_trae_ingresos(self):
        serie = self._get(self.URL, periodo="anio")["serie"]
        self.assertEqual(serie[10]["ingresos"], "3045.00")  # noviembre
        self.assertEqual(serie[10]["ingresos_por_categoria"][str(self.sueldo.pk)], "2500.00")

    def test_ingresos_por_categoria_con_dias_promedio_y_mejor_dia(self):
        cats = self._get(self.URL, periodo="mes")["por_categoria_ingresos"]
        self.assertEqual([c["nombre"] for c in cats], ["Sueldo", "InDrive", "Sin categoría"])
        indrive = cats[1]
        self.assertEqual(indrive["total"], "395.00")
        self.assertEqual(indrive["dias"], 3)  # 2, 17 y 19
        self.assertEqual(indrive["promedio_por_dia"], "131.67")
        self.assertEqual(indrive["mejor_dia"], {"fecha": "2026-11-02", "total": "300.00"})
        self.assertEqual(indrive["porcentaje"], 13)  # 395 de 3045

    def test_la_semana_solo_cuenta_sus_dias(self):
        cats = self._get(self.URL, periodo="semana")["por_categoria_ingresos"]
        indrive = next(c for c in cats if c["nombre"] == "InDrive")
        self.assertEqual((indrive["total"], indrive["dias"], indrive["promedio_por_dia"]),
                         ("95.00", 2, "47.50"))
        self.assertEqual(indrive["mejor_dia"]["fecha"], "2026-11-19")


class MovimientosApiTests(ApiBase):
    URL = "/panel/api/movimientos/"

    def test_lista_del_mes_mas_recientes_primero(self):
        d = self._get(self.URL)
        self.assertEqual(d["total"], 6)
        ids = [m["id"] for m in d["resultados"]]
        self.assertEqual(ids[:2], [self.ana.pk, self.taxi.pk])
        self.assertNotIn(self.ajeno.pk, ids)

    def test_formato_de_cada_movimiento(self):
        m = self._get(self.URL)["resultados"][0]
        self.assertEqual(m["monto"], "18.50")  # texto, no número
        self.assertEqual(m["fecha_hora"], "2026-11-20T09:00:00-05:00")
        self.assertEqual(m["categoria"]["nombre"], "Comida")
        self.assertEqual(m["fuente"], "yape")

    def test_filtros(self):
        casos = {
            "tipo=ingreso": ({"tipo": "ingreso"}, 1),
            "sin categoría": ({"categoria": "sin"}, 1),
            "Compras": ({"categoria": str(self.compras.pk)}, 2),
            "búsqueda sin mayúsculas": ({"q": "ANA G"}, 1),
            "búsqueda en descripción": ({"q": "zapa"}, 1),
        }
        for nombre, (params, esperado) in casos.items():
            with self.subTest(nombre):
                self.assertEqual(self._get(self.URL, **params)["total"], esperado)

    def test_movimientos_de_un_dia(self):
        d = self._get(self.URL, periodo="dia", fecha="2026-11-19")
        self.assertEqual([m["id"] for m in d["resultados"]], [self.taxi.pk])
        self.assertEqual(self.client.get(self.URL, {"periodo": "dia"}).status_code, 400)

    def test_filtros_invalidos(self):
        for params in ({"tipo": "robo"}, {"categoria": "1 OR 1=1"}, {"periodo": "x"}):
            with self.subTest(params):
                self.assertEqual(self.client.get(self.URL, params).status_code, 400)

    @patch("panel.api.POR_PAGINA", 2)
    def test_paginacion(self):
        d = self._get(self.URL, pagina="2")
        self.assertEqual((d["pagina"], d["paginas"], len(d["resultados"])), (2, 3, 2))
        self.assertEqual(self._get(self.URL, pagina="999")["pagina"], 3)  # la última
        self.assertEqual(self._get(self.URL, pagina="abc")["pagina"], 1)


class EditarApiTests(ApiBase):
    def _cambiar(self, tx_id, cuerpo):
        return self.client.post(f"/panel/api/movimientos/{tx_id}/categoria/",
                                json.dumps(cuerpo), content_type="application/json")

    def test_cambiar_categoria_de_un_yape_actualiza_la_regla(self):
        r = self._cambiar(self.juan.pk, {"categoria_id": self.comida.pk})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["regla_actualizada"])
        self.assertEqual(r.json()["movimiento"]["categoria"]["nombre"], "Comida")
        regla = ReglaCategoria.objects.get(usuario=self.u, contraparte="juan p.")
        self.assertEqual(regla.categoria, self.comida)

    def test_cambiar_categoria_de_texto_no_crea_regla(self):
        r = self._cambiar(self.taxi.pk, {"categoria_id": self.compras.pk})
        self.assertFalse(r.json()["regla_actualizada"])
        self.assertFalse(ReglaCategoria.objects.exists())

    def test_no_se_puede_tocar_lo_ajeno_ni_un_ingreso(self):
        for tx in (self.ajeno, self.ingreso):
            with self.subTest(tx=tx.descripcion or tx.contraparte):
                self.assertEqual(self._cambiar(tx.pk, {"categoria_id": self.comida.pk}).status_code, 404)

    def test_cuerpo_invalido(self):
        for cuerpo in ({}, {"categoria_id": "abc"}, ["x"]):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(self._cambiar(self.taxi.pk, cuerpo).status_code, 400)

    def test_borrar_un_yape(self):
        r = self.client.delete(f"/panel/api/movimientos/{self.ana.pk}/")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Transaccion.objects.filter(pk=self.ana.pk).exists())

    def test_borrar_lo_ajeno_da_404_y_no_borra(self):
        r = self.client.delete(f"/panel/api/movimientos/{self.ajeno.pk}/")
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Transaccion.objects.filter(pk=self.ajeno.pk).exists())

    def test_metodos_no_permitidos(self):
        self.assertEqual(self.client.get(f"/panel/api/movimientos/{self.taxi.pk}/").status_code, 405)
        self.assertEqual(
            self.client.get(f"/panel/api/movimientos/{self.taxi.pk}/categoria/").status_code, 405)

    def test_borrar_exige_token_csrf(self):
        navegador = Client(enforce_csrf_checks=True)  # el Client normal se salta el CSRF
        _iniciar_sesion(navegador, self.u)
        url = f"/panel/api/movimientos/{self.taxi.pk}/"

        self.assertEqual(navegador.delete(url).status_code, 403)

        navegador.get("/panel/")  # la página deja la cookie csrftoken, como hará React
        token = navegador.cookies["csrftoken"].value
        self.assertEqual(navegador.delete(url, HTTP_X_CSRFTOKEN=token).status_code, 204)


class CategoriasApiTests(ApiBase):
    def test_sistema_mas_las_propias_sin_las_ajenas(self):
        Categoria.objects.create(nombre="Mascotas", usuario=self.u)
        Categoria.objects.create(nombre="Secreta", usuario=self.otro)
        nombres = [c["nombre"] for c in self._get("/panel/api/categorias/")["categorias"]]
        self.assertIn("Comida", nombres)
        self.assertIn("Mascotas", nombres)
        self.assertNotIn("Secreta", nombres)

    def test_cada_categoria_dice_su_tipo(self):
        cats = {c["nombre"]: c["tipo"] for c in self._get("/panel/api/categorias/")["categorias"]}
        self.assertEqual((cats["Comida"], cats["InDrive"], cats["Sueldo"]), ("gasto", "ingreso", "ingreso"))


class CrearYEditarApiTests(ApiBase):
    URL = "/panel/api/movimientos/"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.indrive = Categoria.objects.get(nombre="InDrive", usuario=None)

    def setUp(self):
        super().setUp()
        # El servicio calcula su propio "ahora" con timezone.now. Este parche es global
        # (afecta a todo Django durante el test), por eso usa el mismo día que _hoy.
        parche = patch("finanzas.servicios.timezone.now", return_value=_lima(2026, 11, 20, 21))
        parche.start()
        self.addCleanup(parche.stop)

    def _enviar(self, metodo, url, cuerpo, cliente=None, **extra):
        cliente = cliente or self.client
        return getattr(cliente, metodo)(url, json.dumps(cuerpo), content_type="application/json", **extra)

    def _crear(self, **cambios):
        cuerpo = {"tipo": "ingreso", "monto": "45.00", "fecha": "2026-11-20",
                  "categoria_id": self.indrive.pk, **cambios}
        return self._enviar("post", self.URL, cuerpo)

    def test_crear_ingreso_de_indrive(self):
        r = self._crear(descripcion="Noche")
        self.assertEqual(r.status_code, 201, r.content)
        m = r.json()["movimiento"]
        self.assertEqual((m["tipo"], m["monto"], m["fuente"], m["descripcion"]),
                         ("ingreso", "45.00", "panel", "Noche"))
        self.assertEqual(m["categoria"]["nombre"], "InDrive")
        self.assertEqual(m["fecha_hora"], "2026-11-20T21:00:00-05:00")
        # Ya cuenta en el resumen del día
        self.assertEqual(self._get("/panel/api/resumen/", periodo="hoy")["totales"]["ingresos"], "45.00")

    def test_crear_con_datos_invalidos_dice_que_campo(self):
        casos = {
            "monto como número de JSON": ({"monto": 45.5}, "monto"),
            "monto que no es número": ({"monto": "cuarenta"}, "monto"),
            "monto en cero": ({"monto": "0.00"}, "monto"),
            "fecha mal escrita": ({"fecha": "20/11/2026"}, "fecha"),
            "fecha futura": ({"fecha": "2026-11-21"}, "fecha"),
            "categoría como texto": ({"categoria_id": "3"}, "categoria_id"),
            "categoría como booleano": ({"categoria_id": True}, "categoria_id"),
            "campo de más": ({"usuario": self.otro.pk}, "usuario"),
            "tipo inválido": ({"tipo": "robo"}, "tipo"),
        }
        for nombre, (cambios, campo) in casos.items():
            with self.subTest(nombre):
                r = self._crear(**cambios)
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.json(), {"error": "datos_invalidos", "campo": campo})
        self.assertFalse(Transaccion.objects.filter(fuente="panel").exists())

    def test_crear_exige_tipo_monto_y_fecha(self):
        r = self._enviar("post", self.URL, {"monto": "10.00", "fecha": "2026-11-20"})
        self.assertEqual(r.json()["campo"], "tipo")
        self.assertEqual(self._enviar("post", self.URL, ["x"]).status_code, 400)

    def test_crear_con_categoria_ajena_o_de_otro_tipo_da_404(self):
        ajena = Categoria.objects.create(nombre="Secreta", usuario=self.otro)
        for cambios in ({"categoria_id": ajena.pk, "tipo": "gasto"}, {"categoria_id": self.comida.pk}):
            with self.subTest(cambios):
                self.assertEqual(self._crear(**cambios).status_code, 404)

    def test_editar_solo_lo_que_viene(self):
        r = self._enviar("patch", f"{self.URL}{self.taxi.pk}/", {"monto": "7.50"})
        self.assertEqual(r.status_code, 200, r.content)
        self.taxi.refresh_from_db()
        self.assertEqual((self.taxi.monto, self.taxi.descripcion), (Decimal("7.50"), "taxi"))

    def test_editar_un_yape_no_permite_cambiar_el_monto(self):
        r = self._enviar("patch", f"{self.URL}{self.ana.pk}/", {"monto": "1.00"})
        self.assertEqual(r.json(), {"error": "datos_invalidos", "campo": "monto_no_editable"})
        r = self._enviar("patch", f"{self.URL}{self.ana.pk}/", {"descripcion": "Menú"})
        self.assertEqual(r.json()["movimiento"]["descripcion"], "Menú")

    def test_editar_lo_ajeno_da_404_y_no_lo_cambia(self):
        r = self._enviar("patch", f"{self.URL}{self.ajeno.pk}/", {"monto": "1.00"})
        self.assertEqual(r.status_code, 404)
        self.ajeno.refresh_from_db()
        self.assertEqual(self.ajeno.monto, Decimal("500.00"))

    def test_ahora_se_puede_categorizar_un_ingreso(self):
        r = self.client.post(f"{self.URL}{self.ingreso.pk}/categoria/",
                             json.dumps({"categoria_id": self.indrive.pk}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["regla_actualizada"])  # los ingresos no aprenden reglas

    def test_crear_y_editar_exigen_token_csrf(self):
        navegador = Client(enforce_csrf_checks=True)
        _iniciar_sesion(navegador, self.u)
        cuerpo = {"tipo": "gasto", "monto": "5.00", "fecha": "2026-11-20"}
        self.assertEqual(self._enviar("post", self.URL, cuerpo, navegador).status_code, 403)
        self.assertEqual(
            self._enviar("patch", f"{self.URL}{self.taxi.pk}/", {"monto": "1.00"}, navegador).status_code, 403)

        navegador.get("/panel/")
        token = navegador.cookies["csrftoken"].value
        r = self._enviar("post", self.URL, cuerpo, navegador, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 201)

    def test_sin_sesion_responde_401(self):
        r = self._enviar("post", self.URL, {}, Client())
        self.assertEqual(r.status_code, 401)
