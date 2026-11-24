from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from finanzas.models import Usuario

from .models import TokenAcceso
from .servicios import canjear_token, cerrar_sesiones, crear_enlace

BASE = "https://panel.test"


def _token_de(url: str) -> str:
    """'https://panel.test/panel/entrar/abc/' -> 'abc'"""
    return url.rstrip("/").rsplit("/", 1)[-1]


@override_settings(PANEL_URL_BASE=BASE)
class EnlaceTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(telefono_wa="51999999999", nombre="Gonzalo")

    def test_crea_url_completa_y_guarda_solo_el_hash(self):
        url = crear_enlace(self.usuario)
        token = _token_de(url)

        self.assertTrue(url.startswith(f"{BASE}/panel/entrar/"))
        guardado = TokenAcceso.objects.get(usuario=self.usuario)
        self.assertNotEqual(guardado.token_hash, token)  # el token NO está en la BD
        self.assertEqual(len(guardado.token_hash), 64)

    def test_vence_en_10_minutos(self):
        crear_enlace(self.usuario)
        t = TokenAcceso.objects.get()
        self.assertAlmostEqual(
            (t.expira_en - t.creado_en).total_seconds(), 600, delta=2
        )

    def test_un_enlace_nuevo_anula_el_anterior(self):
        viejo = _token_de(crear_enlace(self.usuario))
        nuevo = _token_de(crear_enlace(self.usuario))

        self.assertIsNone(canjear_token(viejo))
        self.assertEqual(canjear_token(nuevo), self.usuario)

    def test_se_canjea_una_sola_vez(self):
        token = _token_de(crear_enlace(self.usuario))
        self.assertEqual(canjear_token(token), self.usuario)
        self.assertIsNone(canjear_token(token))

    def test_token_vencido_no_sirve(self):
        token = _token_de(crear_enlace(self.usuario))
        TokenAcceso.objects.update(expira_en=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(canjear_token(token))

    def test_usuario_desactivado_no_puede_entrar(self):
        token = _token_de(crear_enlace(self.usuario))
        Usuario.objects.update(activo=False)
        self.assertIsNone(canjear_token(token))

    def test_token_inventado_no_sirve(self):
        self.assertIsNone(canjear_token("esto-no-existe"))


@override_settings(PANEL_URL_BASE=BASE)
class FlujoAccesoTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(telefono_wa="51999999999", nombre="Gonzalo")

    def _url_entrar(self):
        return crear_enlace(self.usuario).removeprefix(BASE)

    def _entrar(self):
        r = self.client.post(self._url_entrar())
        self.assertRedirects(r, "/panel/", fetch_redirect_response=False)

    def test_get_muestra_boton_y_no_gasta_el_token(self):
        url = self._url_entrar()

        r = self.client.get(url)
        self.assertContains(r, "Entrar a tu panel")
        self.assertContains(r, 'method="post"')
        # Un robot de vista previa hizo GET: el token debe seguir sirviendo
        self.client.get(url)
        self.assertRedirects(self.client.post(url), "/panel/", fetch_redirect_response=False)

    def test_post_inicia_sesion_y_el_panel_carga_react(self):
        self._entrar()
        r = self.client.get("/panel/")
        self.assertContains(r, '<div id="root"></div>', html=False)
        self.assertContains(r, "panel/panel.js")
        self.assertContains(r, '"nombre": "Gonzalo"')  # datos iniciales para React
        self.assertIn("csrftoken", r.cookies)  # React la necesita para POST/DELETE

    def test_un_nombre_malicioso_no_rompe_la_pagina(self):
        self.usuario.nombre = "</script><script>alert(1)</script>"
        self.usuario.save()
        self._entrar()
        r = self.client.get("/panel/")
        self.assertNotContains(r, "</script><script>alert(1)")

    def test_la_sesion_dura_30_dias(self):
        self._entrar()
        self.client.get("/panel/")
        edad = self.client.session.get_expiry_age()
        self.assertAlmostEqual(edad, 30 * 24 * 3600, delta=60)

    def test_enlace_vencido_o_usado_responde_410(self):
        url = self._url_entrar()
        self.client.post(url)
        self.client.logout()

        for metodo in (self.client.get, self.client.post):
            with self.subTest(metodo=metodo.__name__):
                r = metodo(url)
                self.assertEqual(r.status_code, 410)
                self.assertContains(r, "ya no es válido", status_code=410)

    def test_sin_sesion_redirige_a_la_pagina_de_acceso(self):
        r = self.client.get("/panel/")
        self.assertRedirects(r, "/panel/acceso/")
        self.assertContains(self.client.get("/panel/acceso/"), "<code>panel</code>", html=False)

    def test_salir_cierra_solo_este_dispositivo(self):
        self._entrar()
        r = self.client.post("/panel/salir/")
        self.assertRedirects(r, "/panel/acceso/?salio=1")
        self.assertRedirects(self.client.get("/panel/"), "/panel/acceso/")

    def test_salir_por_get_no_esta_permitido(self):
        self._entrar()
        self.assertEqual(self.client.get("/panel/salir/").status_code, 405)
        self.assertEqual(self.client.get("/panel/").status_code, 200)  # sigue dentro

    def test_comando_salir_cierra_todos_los_dispositivos(self):
        self._entrar()
        cerrar_sesiones(self.usuario)
        self.assertRedirects(self.client.get("/panel/"), "/panel/acceso/")

    def test_usuario_desactivado_pierde_la_sesion(self):
        self._entrar()
        Usuario.objects.update(activo=False)
        self.assertRedirects(self.client.get("/panel/"), "/panel/acceso/")

    def test_cambia_el_id_de_sesion_al_entrar(self):
        self.client.get("/panel/acceso/")
        self.client.session.save()
        antes = self.client.session.session_key
        self._entrar()
        self.assertNotEqual(self.client.session.session_key, antes)

    def test_el_panel_no_se_guarda_en_cache(self):
        self._entrar()
        r = self.client.get("/panel/")
        self.assertIn("no-store", r["Cache-Control"])
