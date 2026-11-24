import json
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from finanzas.models import Categoria, Transaccion, Usuario
from finanzas.servicios import LIMA

from .demo import TELEFONO_DEMO, generar_movimientos, usuario_demo
from .sesion import CLAVE_DEMO, CLAVE_USUARIO, CLAVE_VERSION

LUNES_18H = datetime(2026, 11, 23, 18, 0, tzinfo=LIMA)


def _huella(transacciones):
    """Lo que define a un movimiento, para comparar dos generaciones."""
    return sorted((t.tipo, t.monto, t.fecha_hora, t.descripcion, t.contraparte,
                   t.categoria.nombre if t.categoria else None, t.fuente, t.numero_operacion)
                  for t in transacciones)


def _seed(*args, ahora=LUNES_18H):
    # Parcheamos el reloj de Django: el comando no recibe `ahora` desde la terminal
    with patch("django.utils.timezone.now", return_value=ahora):
        call_command("seed_demo", *args, stdout=StringIO())


class SeedDemoTests(TestCase):
    def setUp(self):
        self.real = Usuario.objects.create(telefono_wa="51999999999", nombre="Gonzalo")
        self.mio = Transaccion.objects.create(
            usuario=self.real, tipo="gasto", monto=Decimal("18.50"), fecha_hora=LUNES_18H,
            fuente="texto", descripcion="Almuerzo")

    def _de_la_demo(self):
        return Transaccion.objects.filter(usuario__telefono_wa=TELEFONO_DEMO).select_related("categoria")

    def test_crea_el_usuario_demo_con_nombre_configurable(self):
        with override_settings(PANEL_DEMO_NOMBRE="Lucía"):
            _seed()
        demo = Usuario.objects.get(telefono_wa=TELEFONO_DEMO)
        self.assertEqual(demo.nombre, "Lucía")
        self.assertFalse(demo.telefono_wa.isdigit())  # nunca puede ser un "from" de Meta

    def test_reset_es_idempotente(self):
        _seed("--reset")
        primera = _huella(self._de_la_demo())
        _seed("--reset")
        self.assertEqual(_huella(self._de_la_demo()), primera)
        self.assertGreater(len(primera), 200)  # ~90 días de movimientos

    def test_sin_reset_no_duplica(self):
        _seed()
        cantidad = self._de_la_demo().count()
        _seed()
        self.assertEqual(self._de_la_demo().count(), cantidad)

    def test_no_toca_los_movimientos_de_otros_usuarios(self):
        _seed("--reset")
        _seed("--reset")
        self.assertEqual(list(Transaccion.objects.filter(usuario=self.real)), [self.mio])

    def test_hay_datos_hoy_y_ninguno_en_el_futuro(self):
        _seed("--reset")
        movs = self._de_la_demo()
        self.assertTrue(movs.filter(fecha_hora__date=date(2026, 11, 23)).exists())
        self.assertFalse(movs.filter(fecha_hora__gt=LUNES_18H).exists())
        self.assertFalse(movs.filter(monto__lte=0).exists())

    def test_trae_sueldo_indrive_y_yapes_con_numero(self):
        _seed("--reset")
        movs = self._de_la_demo()
        self.assertTrue(movs.filter(categoria__nombre="Sueldo").exists())
        self.assertGreaterEqual(movs.filter(categoria__nombre="InDrive").count(), 10)
        yapes = movs.filter(fuente="yape")
        self.assertTrue(yapes.exists())
        self.assertFalse(yapes.filter(numero_operacion__isnull=True).exists())
        self.assertTrue(movs.filter(fuente="texto").exists())

    def test_cada_dia_genera_lo_mismo_sin_importar_la_hora_del_reset(self):
        demo = usuario_demo()
        a_las_10 = generar_movimientos(demo, LUNES_18H.replace(hour=10))
        a_las_18 = generar_movimientos(demo, LUNES_18H)
        hoy = date(2026, 11, 23)

        def antes_de_hoy(ts):
            return _huella(t for t in ts if t.fecha_hora.astimezone(LIMA).date() < hoy)

        def de_hoy(ts):
            return [t for t in ts if t.fecha_hora.astimezone(LIMA).date() == hoy]

        self.assertEqual(antes_de_hoy(a_las_10), antes_de_hoy(a_las_18))
        self.assertGreater(len(de_hoy(a_las_18)), len(de_hoy(a_las_10)))
        # Lo de hoy que ya existía a las 10 sigue igual a las 18 (no se "re-sortea")
        self.assertLessEqual(set(_huella(de_hoy(a_las_10))), set(_huella(de_hoy(a_las_18))))


@override_settings(PANEL_DEMO_ACTIVO=True)
class DemoPanelTests(TestCase):
    URL = "/panel/demo/"

    @classmethod
    def setUpTestData(cls):
        cls.demo = usuario_demo()
        cls.comida = Categoria.objects.get(nombre="Comida", usuario=None)
        cls.mov_demo = Transaccion.objects.create(
            usuario=cls.demo, tipo="gasto", monto=Decimal("12.00"), fuente="texto",
            fecha_hora=LUNES_18H, descripcion="Menú", categoria=cls.comida)
        cls.real = Usuario.objects.create(telefono_wa="51999999999", nombre="Gonzalo")
        cls.mov_real = Transaccion.objects.create(
            usuario=cls.real, tipo="gasto", monto=Decimal("999.00"), fuente="texto",
            fecha_hora=LUNES_18H, descripcion="Secreto")

    def setUp(self):
        # "Hoy" fijo, como en test_api: sin esto el test fallaría pasada la medianoche
        parche = patch("panel.api._hoy", return_value=LUNES_18H.date())
        parche.start()
        self.addCleanup(parche.stop)

    def _entrar(self, cliente=None):
        cliente = cliente or self.client
        r = cliente.get(self.URL)
        self.assertRedirects(r, "/panel/", fetch_redirect_response=False)
        return r

    def test_apagada_da_404(self):
        with override_settings(PANEL_DEMO_ACTIVO=False):
            self.assertEqual(self.client.get(self.URL).status_code, 404)

    def test_entra_como_demo_por_2_horas_y_sin_indexar(self):
        r = self._entrar()
        self.assertIn("noindex", r["X-Robots-Tag"])
        s = self.client.session
        self.assertEqual((s[CLAVE_USUARIO], s[CLAVE_DEMO]), (self.demo.pk, True))
        self.assertLessEqual(s.get_expiry_age(), 2 * 3600)

    def test_usar_la_api_no_alarga_la_sesion_demo(self):
        self._entrar()
        vence = self.client.session.get_expiry_date()
        self.client.get("/panel/api/resumen/", {"periodo": "mes"})
        self.assertEqual(self.client.session.get_expiry_date(), vence)

    def test_la_pagina_avisa_que_es_demo(self):
        self._entrar()
        r = self.client.get("/panel/")
        self.assertIn("noindex", r["X-Robots-Tag"])
        self.assertEqual(r.context["datos_iniciales"], {"nombre": "Carlos", "es_demo": True})

    def test_lectura_funciona_y_no_ve_lo_ajeno(self):
        self._entrar()
        for url in ("/panel/api/resumen/", "/panel/api/movimientos/", "/panel/api/categorias/"):
            with self.subTest(url):
                self.assertEqual(self.client.get(url, {"periodo": "hoy"}).status_code, 200)
        lista = self.client.get("/panel/api/movimientos/", {"periodo": "hoy"}).json()
        self.assertEqual([m["id"] for m in lista["resultados"]], [self.mov_demo.pk])
        resumen = self.client.get("/panel/api/resumen/", {"periodo": "hoy"}).json()
        self.assertEqual(resumen["totales"]["gastos"], "12.00")  # sin los 999 del usuario real

    def test_toda_escritura_da_403_aunque_traiga_csrf(self):
        navegador = Client(enforce_csrf_checks=True)
        self._entrar(navegador)
        navegador.get("/panel/")  # deja la cookie csrftoken, como en el navegador real
        token = navegador.cookies["csrftoken"].value
        tx = f"/panel/api/movimientos/{self.mov_demo.pk}/"
        intentos = [
            ("post", "/panel/api/movimientos/", {"tipo": "gasto", "monto": "1.00", "fecha": "2026-11-01"}),
            ("patch", tx, {"monto": "1.00"}),
            ("delete", tx, None),
            ("post", f"{tx}categoria/", {"categoria_id": self.comida.pk}),
        ]
        for metodo, url, cuerpo in intentos:
            with self.subTest(metodo=metodo, url=url):
                r = getattr(navegador, metodo)(url, json.dumps(cuerpo) if cuerpo else "",
                                               content_type="application/json", HTTP_X_CSRFTOKEN=token)
                self.assertEqual(r.status_code, 403)
                self.assertEqual(r.json(), {"error": "demo_solo_lectura"})
        self.mov_demo.refresh_from_db()
        self.assertEqual(self.mov_demo.monto, Decimal("12.00"))
        self.assertEqual(Transaccion.objects.filter(usuario=self.demo).count(), 1)

    def test_no_reemplaza_una_sesion_real(self):
        s = self.client.session
        s[CLAVE_USUARIO], s[CLAVE_VERSION] = self.real.pk, self.real.sesion_version
        s.save()
        self._entrar()
        s = self.client.session
        self.assertEqual(s[CLAVE_USUARIO], self.real.pk)
        self.assertNotIn(CLAVE_DEMO, s)

    def test_salir_de_la_demo_solo_cierra_esa_sesion(self):
        self._entrar()
        version = self.demo.sesion_version
        self.client.post("/panel/salir/")
        self.assertNotIn(CLAVE_USUARIO, self.client.session)
        self.demo.refresh_from_db()
        self.assertEqual(self.demo.sesion_version, version)  # no cierra otras sesiones demo


class TareasProgramadasTests(TestCase):
    """La demo se regenera sola con django-q2 (en el servidor no hay cron para botfin)."""

    def test_la_migracion_programa_las_dos_tareas(self):
        from django_q.models import Schedule

        tareas = {s.func: s for s in Schedule.objects.all()}
        self.assertEqual(tareas["panel.tareas.regenerar_demo"].schedule_type, Schedule.HOURLY)
        self.assertEqual(tareas["panel.tareas.limpiar_sesiones"].schedule_type, Schedule.DAILY)
        self.assertTrue(all(s.repeats == -1 for s in tareas.values()))  # para siempre

    @override_settings(PANEL_DEMO_ACTIVO=False)
    def test_con_la_demo_apagada_no_hace_nada(self):
        from .tareas import regenerar_demo

        regenerar_demo()
        self.assertFalse(Usuario.objects.filter(telefono_wa=TELEFONO_DEMO).exists())

    @override_settings(PANEL_DEMO_ACTIVO=True)
    def test_con_la_demo_activa_regenera(self):
        from .tareas import regenerar_demo

        with patch("django.utils.timezone.now", return_value=LUNES_18H):
            regenerar_demo()
            primera = Transaccion.objects.filter(usuario__telefono_wa=TELEFONO_DEMO).count()
            regenerar_demo()  # la hora siguiente: reemplaza, no duplica
        self.assertGreater(primera, 200)
        self.assertEqual(Transaccion.objects.filter(usuario__telefono_wa=TELEFONO_DEMO).count(), primera)

    def test_limpiar_sesiones_borra_solo_las_vencidas(self):
        from django.contrib.sessions.backends.db import SessionStore
        from django.contrib.sessions.models import Session

        from .tareas import limpiar_sesiones

        vencida, vigente = SessionStore(), SessionStore()
        vencida.set_expiry(-60)
        vencida.save()
        vigente.save()
        limpiar_sesiones()
        self.assertEqual(list(Session.objects.values_list("session_key", flat=True)), [vigente.session_key])
