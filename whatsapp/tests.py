import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from .models import MensajeProcesado

APP_SECRET = "secreto-de-prueba"
MI_NUMERO = "51999999999"
URL = "/whatsapp/webhook/"


def _payload(mensajes=None, statuses=None):
    value = {"messaging_product": "whatsapp"}
    if mensajes is not None:
        value["messages"] = mensajes
    if statuses is not None:
        value["statuses"] = statuses
    return {"object": "whatsapp_business_account",
            "entry": [{"changes": [{"field": "messages", "value": value}]}]}


def _texto(body="hola", wamid="wamid.1", remitente=MI_NUMERO):
    return {"from": remitente, "id": wamid, "type": "text", "text": {"body": body}}


@override_settings(
    WHATSAPP_APP_SECRET=APP_SECRET,
    WHATSAPP_VERIFY_TOKEN="verify-de-prueba",
    WHATSAPP_NUMEROS_PERMITIDOS={MI_NUMERO},
)
@patch("whatsapp.procesador.async_task")
class WebhookTests(TestCase):
    def _post(self, payload, firmar=True):
        cuerpo = json.dumps(payload).encode()
        headers = {}
        if firmar:
            firma = hmac.new(APP_SECRET.encode(), cuerpo, hashlib.sha256).hexdigest()
            headers["HTTP_X_HUB_SIGNATURE_256"] = f"sha256={firma}"
        return self.client.post(URL, cuerpo, content_type="application/json", **headers)

    def test_verificacion_con_token_correcto_devuelve_challenge(self, enviar):
        r = self.client.get(URL, {"hub.mode": "subscribe",
                                  "hub.verify_token": "verify-de-prueba",
                                  "hub.challenge": "123"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"123")

    def test_post_sin_firma_es_rechazado(self, enviar):
        r = self._post(_payload([_texto()]), firmar=False)
        self.assertEqual(r.status_code, 403)
        enviar.assert_not_called()

    def test_texto_de_numero_permitido_se_encola(self, encolar):
        mensaje = _texto("hola bot")
        r = self._post(_payload([mensaje]))
        self.assertEqual(r.status_code, 200)
        encolar.assert_called_once_with("whatsapp.tareas.atender_mensaje", mensaje, "")

    def test_numero_no_permitido_se_ignora(self, enviar):
        self._post(_payload([_texto(remitente="51111111111")]))
        enviar.assert_not_called()
        self.assertFalse(MensajeProcesado.objects.exists())

    def test_mensaje_duplicado_se_responde_una_sola_vez(self, enviar):
        self._post(_payload([_texto(wamid="wamid.repetido")]))
        self._post(_payload([_texto(wamid="wamid.repetido")]))
        enviar.assert_called_once()
        self.assertEqual(MensajeProcesado.objects.count(), 1)

    def test_nombre_de_perfil_se_pasa_a_la_tarea(self, encolar):
        payload = _payload([_texto()])
        payload["entry"][0]["changes"][0]["value"]["contacts"] = [
            {"wa_id": MI_NUMERO, "profile": {"name": "Gonzalo"}}
        ]
        self._post(payload)
        self.assertEqual(encolar.call_args.args[2], "Gonzalo")

    def test_aviso_de_estado_sin_messages_no_rompe(self, enviar):
        r = self._post(_payload(statuses=[{"id": "wamid.x", "status": "read"}]))
        self.assertEqual(r.status_code, 200)
        enviar.assert_not_called()

    def test_si_falla_el_encolado_igual_devuelve_200(self, encolar):
        encolar.side_effect = RuntimeError("cola caída")
        with self.assertLogs("whatsapp.views", level="ERROR"):
            r = self._post(_payload([_texto()]))
        self.assertEqual(r.status_code, 200)


@patch("whatsapp.tareas.enviar_texto")
class ComandosTests(TestCase):
    def _responder(self, enviar, texto):
        from .tareas import atender_mensaje

        atender_mensaje(_texto(texto, wamid=f"wamid.{texto}"))
        return enviar.call_args.args[1]

    def test_normalizar_quita_tildes_signos_y_mayusculas(self, enviar):
        from .tareas import normalizar_comando

        for entrada in ("resumen", "Resumen", "  RESÚMEN ", "¡resumen!", "resumen?"):
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_comando(entrada), "resumen")

    def test_ayuda_y_hola_muestran_los_comandos(self, enviar):
        for texto in ("ayuda", "Hola", "menú"):
            with self.subTest(texto=texto):
                self.assertIn("Esto es lo que sé hacer", self._responder(enviar, texto))

    def test_cada_comando_pide_su_periodo(self, enviar):
        casos = {"hoy": "Hoy,", "semana": "Esta semana", "Mes": "📊 ", "resumen": "📊 "}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertIn(esperado, self._responder(enviar, texto))

    @patch("whatsapp.tareas.interpretar")
    def test_los_comandos_no_llaman_a_la_ia(self, interpretar, enviar):
        for texto in ("hoy", "Semana", "ayuda", "panel", "salir"):
            self._responder(enviar, texto)
        interpretar.assert_not_called()

    @override_settings(PANEL_URL_BASE="https://panel.test")
    def test_panel_manda_un_enlace_de_acceso(self, enviar):
        from panel.models import TokenAcceso

        texto = self._responder(enviar, "Panel")
        self.assertIn("https://panel.test/panel/entrar/", texto)
        self.assertIn("10 minutos", texto)
        self.assertEqual(TokenAcceso.objects.count(), 1)

    def test_salir_invalida_las_sesiones(self, enviar):
        from finanzas.models import Usuario

        texto = self._responder(enviar, "salir")
        self.assertIn("cerré tu panel", texto)
        self.assertEqual(Usuario.objects.get(telefono_wa=MI_NUMERO).sesion_version, 1)



@override_settings(WHATSAPP_TOKEN="tk", WHATSAPP_API_VERSION="v25.0")
class DescargarMediaTests(TestCase):
    def _respuesta(self, json_data=None, content=b""):
        from unittest.mock import MagicMock

        r = MagicMock()
        r.json.return_value = json_data
        r.content = content
        r.raise_for_status.return_value = None
        return r

    @patch("whatsapp.client.requests.get")
    def test_descarga_en_dos_pasos_con_token(self, get):
        from .client import descargar_media

        get.side_effect = [
            self._respuesta({"url": "https://lookaside.fbsbx.com/img", "file_size": 2048}),
            self._respuesta(content=b"\xff\xd8\xff-bytes"),
        ]
        self.assertEqual(descargar_media("MEDIA123"), b"\xff\xd8\xff-bytes")
        primera, segunda = get.call_args_list
        self.assertTrue(primera.args[0].endswith("/v25.0/MEDIA123"))
        self.assertEqual(segunda.args[0], "https://lookaside.fbsbx.com/img")
        for llamada in (primera, segunda):  # las DOS llamadas llevan el token
            self.assertEqual(llamada.kwargs["headers"]["Authorization"], "Bearer tk")

    @patch("whatsapp.client.requests.get")
    def test_archivo_muy_grande_no_se_descarga(self, get):
        from .client import MediaDemasiadoGrande, descargar_media

        get.return_value = self._respuesta({"url": "https://x", "file_size": 50 * 1024 * 1024})
        with self.assertRaises(MediaDemasiadoGrande):
            descargar_media("MEDIA123")
        get.assert_called_once()  # nunca se pidió el archivo


JPEG = b"\xff\xd8\xff" + b"0" * 2048


def _imagen(wamid="wamid.img"):
    return {"from": MI_NUMERO, "id": wamid, "type": "image", "image": {"id": "M1"}}


def _comprobante(**extra):
    from comprobantes.schemas import ComprobanteYape

    datos = {"tipo": "enviado", "monto": "1.50", "contraparte": "Juan Per*",
             "celular_ultimos3": "456", "fecha": "2026-11-12", "hora": "14:29",
             "destino": "Yape", "numero_operacion": "10000001"}
    datos.update(extra)
    return ComprobanteYape.model_validate(datos)


class _Uso:
    input_tokens, output_tokens = 3000, 250


class _FlujoBase(TestCase):
    """Parchea todo lo externo (WhatsApp e IA) con setUp en vez de 5 decoradores.

    self.enviado() devuelve (canal, cuerpo, extra) del ÚLTIMO mensaje enviado,
    sin importar si salió como texto, lista o botones.
    """

    def setUp(self):
        self.mocks = {}
        for nombre in ("enviar_texto", "enviar_lista", "enviar_botones", "extraer",
                       "interpretar"):
            patcher = patch(f"whatsapp.tareas.{nombre}")
            self.mocks[nombre] = patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("whatsapp.tareas.descargar_media", return_value=JPEG)
        self.descargar = patcher.start()
        self.addCleanup(patcher.stop)
        self.extraer = self.mocks["extraer"]
        self.extraer.return_value = (_comprobante(), _Uso())
        # Cada envío se anota en orden, por cualquier canal
        self.envios = []
        for canal in ("texto", "lista", "botones"):
            self.mocks[f"enviar_{canal}"].side_effect = (
                lambda *args, canal=canal: self.envios.append((canal, args[1], args[2:]))
            )

    def _atender(self, mensaje=None, nombre="Gonzalo"):
        from .tareas import atender_mensaje

        atender_mensaje(mensaje or _imagen(), nombre)

    def enviado(self):
        return self.envios[-1]


class FlujoYapeTests(_FlujoBase):
    def test_yape_enviado_se_guarda_como_gasto_y_pide_categoria(self):
        from decimal import Decimal

        from finanzas.models import Transaccion

        self._atender()
        t = Transaccion.objects.get()
        self.assertEqual(t.tipo, Transaccion.Tipo.GASTO)
        self.assertEqual(t.monto, Decimal("1.50"))
        self.assertEqual(t.usuario.nombre, "Gonzalo")
        self.assertEqual(t.wamid_origen, "wamid.img")
        self.assertIsNone(t.categoria)
        canal, cuerpo, _ = self.enviado()
        self.assertEqual(canal, "lista")
        self.assertEqual(
            cuerpo,
            "✅ Gasto anotado\nS/ 1.50 → Juan Per*\n📅 12/11 · 2:29 p.m."
            "\n\n¿En qué categoría lo pongo?",
        )

    def test_yape_recibido_es_ingreso_y_no_pide_categoria(self):
        from finanzas.models import Transaccion

        self.extraer.return_value = (_comprobante(
            tipo="recibido", monto="6.00", contraparte="Maria Lop*",
            hora="07:32", numero_operacion="00014890"), _Uso())
        self._atender()
        self.assertEqual(Transaccion.objects.get().tipo, Transaccion.Tipo.INGRESO)
        canal, cuerpo, _ = self.enviado()
        self.assertEqual(canal, "texto")  # sin lista: los ingresos no se categorizan
        self.assertIn("💰 Ingreso anotado\nS/ 6.00 ← Maria Lop*", cuerpo)
        self.assertIn("7:32 a.m.", cuerpo)

    def test_mensaje_del_yape_aparece_en_la_respuesta(self):
        self.extraer.return_value = (_comprobante(mensaje="Pan"), _Uso())
        self._atender()
        self.assertIn("📝 Pan", self.enviado()[1])

    def test_mismo_yape_dos_veces_no_duplica(self):
        from finanzas.models import Transaccion

        self._atender(_imagen("wamid.captura"))
        self._atender(_imagen("wamid.compartida"))  # otro mensaje, misma operación
        self.assertEqual(Transaccion.objects.count(), 1)
        self.assertIn("ya lo tenías anotado", self.enviado()[1])

    def test_imagen_que_no_es_yape_no_guarda_nada(self):
        from comprobantes.schemas import ComprobanteYape
        from finanzas.models import Transaccion

        self.extraer.return_value = (ComprobanteYape(tipo="no_es_comprobante"), _Uso())
        self._atender()
        self.assertFalse(Transaccion.objects.exists())
        self.assertIn("no parece un comprobante", self.enviado()[1])

    def test_extraccion_invalida_pide_reenviar(self):
        from pydantic import ValidationError

        from comprobantes.schemas import ComprobanteYape
        from finanzas.models import Transaccion

        try:
            ComprobanteYape.model_validate({"tipo": "enviado"})
        except ValidationError as e:
            self.extraer.side_effect = e
        # assertLogs: silencia el traceback Y verifica que el error sí se registró
        with self.assertLogs("whatsapp.tareas", level="WARNING"):
            self._atender()
        self.assertFalse(Transaccion.objects.exists())
        self.assertIn("No pude leer", self.enviado()[1])

    def test_archivo_que_no_es_imagen_no_llama_a_la_ia(self):
        self.descargar.return_value = b"esto no es una imagen"
        self._atender()
        self.extraer.assert_not_called()


def _eleccion(id_opcion, wamid="wamid.eleccion", tipo="list_reply"):
    return {"from": MI_NUMERO, "id": wamid, "type": "interactive",
            "interactive": {"type": tipo, tipo: {"id": id_opcion, "title": "x"}}}


class CategorizacionTests(_FlujoBase):
    def setUp(self):
        super().setUp()
        from finanzas.models import Categoria, Transaccion

        self._atender()  # Juan, sin categoría
        self.gasto = Transaccion.objects.get()
        self.comida = Categoria.objects.get(nombre="Comida", usuario=None)
        self.compras = Categoria.objects.get(nombre="Compras", usuario=None)

    def _elegir(self, categoria, gasto=None):
        self._atender(_eleccion(f"cat:{(gasto or self.gasto).pk}:{categoria.pk}"))

    def test_la_lista_trae_las_categorias_con_ids_autocontenidos(self):
        _, _, (boton, filas) = self.enviado()
        self.assertEqual(boton, "Elegir categoría")
        self.assertIn((f"cat:{self.gasto.pk}:{self.comida.pk}", "🍔 Comida"), filas)
        self.assertLessEqual(len(filas), 10)  # límite de WhatsApp

    def test_elegir_categoria_la_asigna_y_crea_la_regla(self):
        from finanzas.models import ReglaCategoria

        self._elegir(self.comida)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.categoria, self.comida)
        regla = ReglaCategoria.objects.get()
        self.assertEqual((regla.contraparte, regla.contraparte_celular3), ("juan per*", "456"))
        self.assertIn("irán solos a Comida", self.enviado()[1])

    def test_siguiente_yape_a_la_misma_persona_se_categoriza_solo(self):
        from finanzas.models import Transaccion

        self._elegir(self.comida)
        self.extraer.return_value = (_comprobante(numero_operacion="99999999"), _Uso())
        self._atender(_imagen("wamid.otro"))
        nuevo = Transaccion.objects.get(numero_operacion="99999999")
        self.assertEqual(nuevo.categoria, self.comida)
        canal, cuerpo, (botones,) = self.enviado()
        self.assertEqual(canal, "botones")  # no pregunta: ofrece cambiar
        self.assertIn("🍔 Comida", cuerpo)
        self.assertEqual(botones, [(f"cambiar:{nuevo.pk}", "Cambiar categoría")])

    def test_la_regla_ignora_mayusculas_y_espacios_de_la_ia(self):
        from finanzas.models import Transaccion

        self._elegir(self.comida)
        self.extraer.return_value = (_comprobante(
            numero_operacion="99999999", contraparte="JUAN  Per*"), _Uso())
        self._atender(_imagen("wamid.otro"))
        self.assertEqual(Transaccion.objects.get(numero_operacion="99999999").categoria,
                         self.comida)

    def test_mismo_nombre_con_otro_celular_no_usa_la_regla(self):
        from finanzas.models import Transaccion

        self._elegir(self.comida)
        self.extraer.return_value = (_comprobante(
            numero_operacion="99999999", celular_ultimos3="555"), _Uso())
        self._atender(_imagen("wamid.otro"))
        self.assertIsNone(Transaccion.objects.get(numero_operacion="99999999").categoria)
        self.assertEqual(self.enviado()[0], "lista")

    def test_cambiar_muestra_la_lista_otra_vez(self):
        self._elegir(self.comida)
        self._atender(_eleccion(f"cambiar:{self.gasto.pk}", "wamid.c", "button_reply"))
        canal, cuerpo, _ = self.enviado()
        self.assertEqual(canal, "lista")
        self.assertIn("¿A qué categoría lo cambio?", cuerpo)

    def test_corregir_actualiza_la_regla_sin_duplicarla(self):
        from finanzas.models import ReglaCategoria

        self._elegir(self.comida)
        self._elegir(self.compras)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.categoria, self.compras)
        self.assertEqual(ReglaCategoria.objects.get().categoria, self.compras)

    def test_no_se_puede_categorizar_un_gasto_ajeno(self):
        from finanzas.models import Transaccion, Usuario

        otro = Usuario.objects.create(telefono_wa="51888888888")
        ajeno = Transaccion.objects.create(
            usuario=otro, tipo="gasto", monto="5.00", fecha_hora=self.gasto.fecha_hora,
            fuente="yape", numero_operacion="1")
        with self.assertLogs("whatsapp.tareas", level="WARNING"):
            self._elegir(self.comida, gasto=ajeno)
        ajeno.refresh_from_db()
        self.assertIsNone(ajeno.categoria)
        self.assertIn("No encontré", self.enviado()[1])

    def test_no_se_puede_categorizar_un_ingreso(self):
        from finanzas.models import Transaccion

        ingreso = Transaccion.objects.create(
            usuario=self.gasto.usuario, tipo="ingreso", monto="6.00",
            fecha_hora=self.gasto.fecha_hora, fuente="yape", numero_operacion="2")
        with self.assertLogs("whatsapp.tareas", level="WARNING"):
            self._elegir(self.comida, gasto=ingreso)
        ingreso.refresh_from_db()
        self.assertIsNone(ingreso.categoria)

    def test_id_manipulado_no_rompe_el_bot(self):
        for basura in ("cat:abc:1", "cat:1", "hackeo", ""):
            with self.subTest(id=basura), self.assertLogs("whatsapp.tareas", level="WARNING"):
                self._atender(_eleccion(basura, wamid=f"wamid.{basura}"))
                self.assertIn("No encontré", self.enviado()[1])


@override_settings(WHATSAPP_TOKEN="tk", WHATSAPP_API_VERSION="v25.0",
                   WHATSAPP_PHONE_NUMBER_ID="PNID")
@patch("whatsapp.client.requests.post")
class EnviarInteractivoTests(TestCase):
    def test_lista_tiene_el_formato_de_meta_y_respeta_limites(self, post):
        from .client import enviar_lista

        filas = [(f"cat:1:{i}", f"Categoría con nombre larguísimo {i}") for i in range(12)]
        enviar_lista(MI_NUMERO, "cuerpo", "Elegir categoría", filas)
        enviado = post.call_args.kwargs["json"]
        self.assertEqual(enviado["type"], "interactive")
        interactivo = enviado["interactive"]
        self.assertEqual(interactivo["type"], "list")
        filas_enviadas = interactivo["action"]["sections"][0]["rows"]
        self.assertEqual(len(filas_enviadas), 10)  # Meta rechaza más de 10
        self.assertTrue(all(len(f["title"]) <= 24 for f in filas_enviadas))

    def test_botones_tienen_el_formato_de_meta(self, post):
        from .client import enviar_botones

        enviar_botones(MI_NUMERO, "cuerpo", [("cambiar:1", "Cambiar categoría")])
        boton = post.call_args.kwargs["json"]["interactive"]["action"]["buttons"][0]
        self.assertEqual(boton, {"type": "reply",
                                 "reply": {"id": "cambiar:1", "title": "Cambiar categoría"}})



def _escrito(body, wamid="wamid.txt", timestamp="1795021200"):  # 18/11/2026 12:00 Lima
    return {"from": MI_NUMERO, "id": wamid, "type": "text", "timestamp": timestamp,
            "text": {"body": body}}


def _interpretacion(clase="movimientos", *movimientos):
    from comprobantes.schemas import InterpretacionTexto

    return InterpretacionTexto.model_validate({"clase": clase, "movimientos": list(movimientos)})


def _mov(monto="2.50", descripcion="Papitas", categoria="Comida", tipo="gasto", dias_atras=0):
    return {"tipo": tipo, "monto": monto, "descripcion": descripcion,
            "categoria": categoria, "dias_atras": dias_atras}


class TextoLibreTests(_FlujoBase):
    def setUp(self):
        super().setUp()
        self.interpretar = self.mocks["interpretar"]

    def _escribir(self, *movimientos, clase="movimientos", body="gasté 2.50 en papitas"):
        self.interpretar.return_value = (_interpretacion(clase, *movimientos), _Uso())
        self._atender(_escrito(body))

    def test_gasto_escrito_se_guarda_con_categoria_y_botones(self):
        from finanzas.models import Transaccion

        self._escribir(_mov())
        t = Transaccion.objects.get()
        self.assertEqual((t.fuente, t.descripcion, t.categoria.nombre),
                         ("texto", "Papitas", "Comida"))
        canal, cuerpo, (botones,) = self.enviado()
        self.assertEqual(canal, "botones")
        self.assertEqual(cuerpo, "✅ Gasto anotado\nS/ 2.50 · Papitas\n🍔 Comida\n📅 18/11 · 12:00 p.m.")
        self.assertEqual(botones, [(f"cambiar:{t.pk}", "Cambiar categoría"),
                                   (f"deshacer:{t.pk}", "Deshacer")])

    def test_la_ia_recibe_las_categorias_de_cada_tipo_y_el_dia(self):
        self._escribir(_mov())
        texto, gasto, ingreso, dia = self.interpretar.call_args.args
        self.assertEqual(texto, "gasté 2.50 en papitas")
        self.assertIn("Comida", gasto)
        self.assertNotIn("InDrive", gasto)
        self.assertEqual(sorted(ingreso), ["InDrive", "Otros ingresos", "Sueldo"])
        self.assertEqual(dia, "miércoles")

    def test_ingreso_de_indrive_escrito_queda_con_su_categoria(self):
        from finanzas.models import Transaccion

        self._escribir(_mov("50.00", "Viajes de InDrive", "InDrive", tipo="ingreso"),
                       body="hoy recibí 50 soles de indrive")
        t = Transaccion.objects.get()
        self.assertEqual((t.tipo, t.categoria.nombre), ("ingreso", "InDrive"))
        canal, cuerpo, (botones,) = self.enviado()
        self.assertEqual(cuerpo, "💰 Ingreso anotado\nS/ 50.00 · Viajes de InDrive\n"
                                 "🚗 InDrive\n📅 18/11 · 12:00 p.m.")
        self.assertEqual(botones, [(f"deshacer:{t.pk}", "Deshacer")])  # sin lista de categorías

    def test_si_la_ia_cruza_los_tipos_no_se_guarda_esa_categoria(self):
        from finanzas.models import Transaccion

        # La IA se equivoca: gasto con "InDrive" e ingreso con "Comida"
        self._escribir(_mov("5.00", "Gasolina", "InDrive"),
                       _mov("40.00", "Viajes", "Comida", tipo="ingreso"))
        gasto, ingreso = Transaccion.objects.order_by("tipo")
        self.assertIsNone(gasto.categoria)  # y el bot le pregunta la categoría con la lista
        self.assertIsNone(ingreso.categoria)
        self.assertEqual(self.envios[0][0], "lista")

    def test_varios_movimientos_un_mensaje_por_cada_uno(self):
        from finanzas.models import Transaccion

        self._escribir(_mov("15.00", "Almuerzo"), _mov("8.00", "Taxi", "Transporte"))
        self.assertEqual(Transaccion.objects.count(), 2)
        self.assertEqual(len(self.envios), 2)
        self.assertIn("Almuerzo", self.envios[0][1])
        self.assertIn("Taxi", self.envios[1][1])

    def test_ingreso_escrito_sin_categoria_solo_con_deshacer(self):
        from finanzas.models import Transaccion

        self._escribir(_mov("50.00", "Trabajo", None, tipo="ingreso"))
        t = Transaccion.objects.get()
        self.assertEqual(t.tipo, "ingreso")
        self.assertIsNone(t.categoria)
        canal, cuerpo, (botones,) = self.enviado()
        self.assertIn("💰 Ingreso anotado\nS/ 50.00 · Trabajo", cuerpo)
        self.assertEqual(botones, [(f"deshacer:{t.pk}", "Deshacer")])

    def test_ayer_usa_la_hora_del_mensaje_menos_un_dia(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from finanzas.models import Transaccion

        self._escribir(_mov(dias_atras=1))
        self.assertEqual(Transaccion.objects.get().fecha_hora,
                         datetime(2026, 11, 17, 12, 0, tzinfo=ZoneInfo("America/Lima")))

    def test_casos_sin_movimientos_no_guardan_nada(self):
        from finanzas.models import Transaccion

        casos = {"no_es_movimiento": "No encontré un gasto",
                 "otra_moneda": "solo anoto montos en soles",
                 "demasiados": "máximo 5"}
        for clase, esperado in casos.items():
            with self.subTest(clase=clase):
                self._escribir(clase=clase)
                self.assertIn(esperado, self.enviado()[1])
        self.assertFalse(Transaccion.objects.exists())

    def test_respuesta_invalida_de_la_ia_no_guarda_nada(self):
        from pydantic import ValidationError

        from finanzas.models import Transaccion

        try:
            _interpretacion("movimientos")  # lista vacía: inválido
        except ValidationError as e:
            self.interpretar.side_effect = e
        with self.assertLogs("whatsapp.tareas", level="WARNING"):
            self._atender(_escrito("gasté algo"))
        self.assertFalse(Transaccion.objects.exists())
        self.assertIn("No te entendí", self.enviado()[1])

    def test_deshacer_borra_el_movimiento_escrito(self):
        from finanzas.models import Transaccion

        self._escribir(_mov())
        t = Transaccion.objects.get()
        self._atender(_eleccion(f"deshacer:{t.pk}", "wamid.d", "button_reply"))
        self.assertFalse(Transaccion.objects.exists())
        self.assertEqual(self.enviado()[1], "🗑️ Listo, borré: S/ 2.50 · Papitas")

    def test_deshacer_dos_veces_no_rompe(self):
        self._escribir(_mov())
        from finanzas.models import Transaccion

        pk = Transaccion.objects.get().pk
        self._atender(_eleccion(f"deshacer:{pk}", "wamid.d1", "button_reply"))
        with self.assertLogs("whatsapp.tareas", level="WARNING"):
            self._atender(_eleccion(f"deshacer:{pk}", "wamid.d2", "button_reply"))
        self.assertIn("No encontré", self.enviado()[1])

    def test_un_yape_no_se_puede_deshacer(self):
        from finanzas.models import Transaccion

        self._atender()  # Yape de Juan
        yape = Transaccion.objects.get()
        with self.assertLogs("whatsapp.tareas", level="WARNING"):
            self._atender(_eleccion(f"deshacer:{yape.pk}", "wamid.d", "button_reply"))
        self.assertTrue(Transaccion.objects.filter(pk=yape.pk).exists())

    def test_cambiar_categoria_de_un_gasto_escrito(self):
        from finanzas.models import Categoria, ReglaCategoria, Transaccion

        self._escribir(_mov())
        t = Transaccion.objects.get()
        otros = Categoria.objects.get(nombre="Otros", usuario=None)
        self._atender(_eleccion(f"cat:{t.pk}:{otros.pk}"))
        t.refresh_from_db()
        self.assertEqual(t.categoria, otros)
        self.assertFalse(ReglaCategoria.objects.exists())  # sin contraparte no hay regla
        self.assertIn("Papitas quedó en Otros", self.enviado()[1])
