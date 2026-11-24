from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Categoria, ReglaCategoria, Transaccion, Usuario

LIMA = ZoneInfo("America/Lima")


class TransaccionConstraintsTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(telefono_wa="51999999999", nombre="Gonzalo")

    def _yape(self, **extra):
        datos = {
            "usuario": self.usuario, "tipo": Transaccion.Tipo.GASTO, "monto": Decimal("1.50"),
            "fecha_hora": datetime(2026, 11, 12, 14, 29, tzinfo=LIMA),
            "contraparte": "Juan Per*", "fuente": Transaccion.Fuente.YAPE,
            "numero_operacion": "10000001",
        }
        datos.update(extra)
        return Transaccion.objects.create(**datos)

    def _falla(self, **extra):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._yape(**extra)

    def test_misma_operacion_de_yape_no_entra_dos_veces(self):
        self._yape()
        self._falla()

    def test_gastos_de_texto_sin_numero_de_operacion_no_chocan(self):
        for _ in range(2):
            self._yape(fuente=Transaccion.Fuente.TEXTO, numero_operacion=None,
                       contraparte="", descripcion="papitas")
        self.assertEqual(Transaccion.objects.count(), 2)

    def test_misma_operacion_en_otro_usuario_si_entra(self):
        self._yape()
        otro = Usuario.objects.create(telefono_wa="51888888888")
        self._yape(usuario=otro)
        self.assertEqual(Transaccion.objects.count(), 2)

    def test_monto_cero_o_negativo_es_rechazado(self):
        self._falla(monto=Decimal("0"), numero_operacion="1")
        self._falla(monto=Decimal("-5.00"), numero_operacion="2")

    def test_yape_sin_numero_de_operacion_es_rechazado(self):
        self._falla(numero_operacion=None)

    def test_monto_conserva_decimales_exactos(self):
        t = self._yape(monto=Decimal("0.10"))
        t.refresh_from_db()
        self.assertEqual(t.monto, Decimal("0.10"))

    def test_ceros_a_la_izquierda_se_conservan(self):
        t = self._yape(tipo=Transaccion.Tipo.INGRESO, numero_operacion="00014890")
        t.refresh_from_db()
        self.assertEqual(t.numero_operacion, "00014890")


class CategoriaTests(TestCase):
    def test_categorias_del_sistema_vienen_precargadas(self):
        nombres = set(Categoria.objects.filter(usuario=None).values_list("nombre", flat=True))
        self.assertTrue({"Comida", "Transporte", "Otros"} <= nombres)

    def test_no_puede_haber_dos_categorias_del_sistema_con_el_mismo_nombre(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Categoria.objects.create(nombre="Comida", usuario=None)

    def test_un_usuario_puede_tener_su_propia_categoria_con_nombre_del_sistema(self):
        u = Usuario.objects.create(telefono_wa="51999999999")
        Categoria.objects.create(nombre="Comida", usuario=u)
        self.assertEqual(Categoria.objects.filter(nombre="Comida").count(), 2)


class ServiciosTests(TestCase):
    def test_obtener_usuario_crea_una_sola_vez(self):
        from .servicios import obtener_usuario

        a = obtener_usuario("51999999999", "Gonzalo")
        b = obtener_usuario("51999999999", "Otro nombre")
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Usuario.objects.get().nombre, "Gonzalo")

    def test_fecha_hora_se_guarda_en_hora_de_lima(self):
        from comprobantes.schemas import ComprobanteYape

        from .servicios import registrar_comprobante

        u = Usuario.objects.create(telefono_wa="51999999999")
        c = ComprobanteYape.model_validate({
            "tipo": "enviado", "monto": "0.10", "contraparte": "Ana Gom*",
            "fecha": "2026-11-13", "hora": "11:40", "numero_operacion": "10000002"})
        t, creada = registrar_comprobante(u, c)
        self.assertTrue(creada)
        # 11:40 en Lima (UTC-5) son las 16:40 UTC
        self.assertEqual(t.fecha_hora, datetime(2026, 11, 13, 16, 40, tzinfo=ZoneInfo("UTC")))


class ResumenTests(TestCase):
    """`ahora` fijo: miércoles 18/11/2026 a las 10:00 de Lima."""

    AHORA = datetime(2026, 11, 18, 10, 0, tzinfo=LIMA)

    def setUp(self):
        self.u = Usuario.objects.create(telefono_wa="51999999999")
        self.comida = Categoria.objects.get(nombre="Comida", usuario=None)
        self.compras = Categoria.objects.get(nombre="Compras", usuario=None)
        self._n = 0

    def _mov(self, monto, cuando, tipo="gasto", categoria=None, usuario=None):
        self._n += 1
        return Transaccion.objects.create(
            usuario=usuario or self.u, tipo=tipo, monto=Decimal(monto), fecha_hora=cuando,
            categoria=categoria, fuente="yape", numero_operacion=str(self._n))

    def _resumen(self, periodo):
        from .resumenes import calcular_resumen

        return calcular_resumen(self.u, periodo, ahora=self.AHORA)

    def test_rangos_de_cada_periodo(self):
        from datetime import date

        from .resumenes import rango

        hoy = date(2026, 11, 18)  # miércoles
        casos = {
            "hoy": (datetime(2026, 11, 18, tzinfo=LIMA), datetime(2026, 11, 19, tzinfo=LIMA)),
            "semana": (datetime(2026, 11, 16, tzinfo=LIMA), datetime(2026, 11, 23, tzinfo=LIMA)),
            "mes": (datetime(2026, 11, 1, tzinfo=LIMA), datetime(2026, 12, 1, tzinfo=LIMA)),
        }
        for periodo, esperado in casos.items():
            with self.subTest(periodo=periodo):
                self.assertEqual(rango(periodo, hoy)[:2], esperado)

    def test_mes_de_diciembre_cruza_al_anio_siguiente(self):
        from datetime import date

        from .resumenes import rango

        _, fin, titulo = rango("mes", date(2026, 12, 31))
        self.assertEqual(fin, datetime(2027, 1, 1, tzinfo=LIMA))
        self.assertEqual(titulo, "Diciembre 2026")

    def test_hoy_usa_la_medianoche_de_lima_no_la_de_utc(self):
        # 23:30 de ayer en Lima = 04:30 UTC de HOY. Es de ayer, no debe contar.
        self._mov("5.00", datetime(2026, 11, 17, 23, 30, tzinfo=LIMA))
        # 00:10 de hoy en Lima = 05:10 UTC. Es de hoy.
        self._mov("2.00", datetime(2026, 11, 18, 0, 10, tzinfo=LIMA))
        self.assertEqual(self._resumen("hoy").total_gastos, Decimal("2.00"))

    def test_agrupa_por_categoria_de_mayor_a_menor(self):
        hoy = datetime(2026, 11, 18, 9, 0, tzinfo=LIMA)
        self._mov("1.50", hoy, categoria=self.compras)
        self._mov("1.50", hoy, categoria=self.compras)
        self._mov("0.10", hoy, categoria=self.comida)
        self._mov("4.00", hoy)  # sin categoría
        self._mov("6.00", hoy, tipo="ingreso")
        r = self._resumen("hoy")
        self.assertEqual(r.gastos, [
            ("❓ Sin categoría", Decimal("4.00")),
            ("🛒 Compras", Decimal("3.00")),
            ("🍔 Comida", Decimal("0.10")),
        ])
        self.assertEqual(r.total_gastos, Decimal("7.10"))  # el total cuadra con las líneas
        self.assertEqual(r.total_ingresos, Decimal("6.00"))
        self.assertEqual(r.movimientos, 5)

    def test_no_mezcla_movimientos_de_otro_usuario(self):
        otro = Usuario.objects.create(telefono_wa="51888888888")
        self._mov("99.00", datetime(2026, 11, 18, 9, 0, tzinfo=LIMA), usuario=otro)
        self.assertEqual(self._resumen("mes").movimientos, 0)

    def test_formato_del_resumen(self):
        from .resumenes import formatear_resumen

        hoy = datetime(2026, 11, 18, 9, 0, tzinfo=LIMA)
        self._mov("3.00", hoy, categoria=self.compras)
        self._mov("1.00", hoy, categoria=self.comida)
        self._mov("1500.00", hoy, tipo="ingreso")
        self.assertEqual(formatear_resumen(self._resumen("mes")), (
            "📊 Noviembre 2026\n\n"
            "💸 Gastos: S/ 4.00\n"
            "   🛒 Compras: S/ 3.00 (75%)\n"
            "   🍔 Comida: S/ 1.00 (25%)\n"
            "💰 Ingresos: S/ 1,500.00\n\n"
            "Balance: +S/ 1,496.00"
        ))

    def test_balance_negativo_y_periodo_vacio(self):
        from .resumenes import formatear_resumen

        self.assertIn("No tienes movimientos", formatear_resumen(self._resumen("hoy")))
        self._mov("10.00", datetime(2026, 11, 18, 9, 0, tzinfo=LIMA))
        self.assertIn("Balance: -S/ 10.00", formatear_resumen(self._resumen("hoy")))


class RangoComparableTests(TestCase):
    """Casos borde del "tramo equivalente" que usa el panel para el % de cambio."""

    def _comparable(self, periodo, hoy):
        from .resumenes import rango_comparable

        inicio, fin, etiqueta = rango_comparable(periodo, hoy)
        return inicio.date(), fin.date(), etiqueta

    def test_un_dia_elegido_se_compara_con_el_dia_anterior(self):
        from datetime import date

        from .resumenes import rango

        inicio, fin, titulo = rango("dia", date(2026, 11, 1))
        self.assertEqual((inicio.date(), fin.date(), titulo),
                         (date(2026, 11, 1), date(2026, 11, 2), "Domingo 1 de noviembre"))
        # El 1 de noviembre se compara con el 31 de octubre (cruza de mes sin problema)
        self.assertEqual(self._comparable("dia", date(2026, 11, 1)),
                         (date(2026, 10, 31), date(2026, 11, 1), "el sábado 31"))

    def test_mes_el_31_de_marzo_no_se_pasa_de_febrero(self):
        from datetime import date

        self.assertEqual(self._comparable("mes", date(2026, 3, 31)),
                         (date(2026, 2, 1), date(2026, 3, 1), "el 1–28 de febrero"))

    def test_mes_en_enero_compara_con_diciembre_del_anio_anterior(self):
        from datetime import date

        self.assertEqual(self._comparable("mes", date(2027, 1, 10)),
                         (date(2026, 12, 1), date(2026, 12, 11), "el 1–10 de diciembre"))

    def test_semana_un_lunes_compara_solo_con_el_lunes_pasado(self):
        from datetime import date

        inicio, fin, _ = self._comparable("semana", date(2026, 11, 16))
        self.assertEqual((inicio, fin), (date(2026, 11, 9), date(2026, 11, 10)))

    def test_anio_un_29_de_febrero(self):
        from datetime import date

        inicio, fin, etiqueta = self._comparable("anio", date(2028, 2, 29))
        self.assertEqual((inicio, fin), (date(2027, 1, 1), date(2027, 3, 1)))
        self.assertEqual(etiqueta, "el mismo tramo de 2027")

    def test_rango_de_mes_pasado_y_anio(self):
        from datetime import date

        from .resumenes import rango

        inicio, fin, titulo = rango("mes_pasado", date(2026, 1, 15))
        self.assertEqual((inicio.date(), fin.date(), titulo),
                         (date(2025, 12, 1), date(2026, 1, 1), "Diciembre 2025"))
        inicio, fin, titulo = rango("anio", date(2026, 11, 20))
        self.assertEqual((inicio.date(), fin.date(), titulo),
                         (date(2026, 1, 1), date(2027, 1, 1), "2026"))


class CategoriasPorTipoTests(TestCase):
    def setUp(self):
        self.u = Usuario.objects.create(telefono_wa="51999999999")

    def test_categorias_de_ingreso_vienen_precargadas(self):
        nombres = set(Categoria.objects.filter(usuario=None, tipo="ingreso")
                      .values_list("nombre", flat=True))
        self.assertEqual(nombres, {"Sueldo", "InDrive", "Otros ingresos"})

    def test_whatsapp_solo_ve_las_de_gasto(self):
        from .servicios import categorias_disponibles

        nombres = [c.nombre for c in categorias_disponibles(self.u)]
        self.assertIn("Comida", nombres)
        self.assertNotIn("InDrive", nombres)
        ingresos = [c.nombre for c in categorias_disponibles(self.u, tipo="ingreso")]
        self.assertEqual(sorted(ingresos), ["InDrive", "Otros ingresos", "Sueldo"])


class MovimientosPanelTests(TestCase):
    """`ahora` fijo: viernes 20/11/2026 a las 21:15 de Lima."""

    AHORA = datetime(2026, 11, 20, 21, 15, tzinfo=LIMA)

    def setUp(self):
        self.u = Usuario.objects.create(telefono_wa="51999999999")
        self.otro = Usuario.objects.create(telefono_wa="51888888888")
        self.comida = Categoria.objects.get(nombre="Comida", usuario=None)
        self.indrive = Categoria.objects.get(nombre="InDrive", usuario=None)

    def _crear(self, **extra):
        from datetime import date

        from .servicios import crear_movimiento_panel

        datos = {"tipo": "ingreso", "monto": Decimal("45.00"), "fecha": date(2026, 11, 20),
                 "categoria_id": self.indrive.pk, "ahora": self.AHORA, **extra}
        return crear_movimiento_panel(self.u, **datos)

    def _editar(self, t, ahora=None, **cambios):
        from .servicios import editar_movimiento_panel

        return editar_movimiento_panel(self.u, t.pk, cambios, ahora=ahora or self.AHORA)

    def test_crear_ingreso_de_hoy_usa_la_hora_actual(self):
        t = self._crear(descripcion="  Viajes de la noche ")
        t.refresh_from_db()
        self.assertEqual((t.tipo, t.monto, t.fuente, t.categoria, t.descripcion),
                         ("ingreso", Decimal("45.00"), "panel", self.indrive, "Viajes de la noche"))
        self.assertEqual(t.fecha_hora, self.AHORA)

    def test_crear_de_otro_dia_queda_a_mediodia(self):
        from datetime import date

        t = self._crear(fecha=date(2026, 11, 18))
        self.assertEqual(t.fecha_hora, datetime(2026, 11, 18, 12, 0, tzinfo=LIMA))

    def test_crear_sin_categoria_ni_descripcion(self):
        t = self._crear(tipo="gasto", categoria_id=None)
        self.assertIsNone(t.categoria)
        self.assertEqual(t.descripcion, "")

    def test_datos_invalidos(self):
        from datetime import date

        from .servicios import DatosInvalidos

        casos = {
            "tipo": {"tipo": "robo"},
            "monto": {"monto": Decimal("0")},
            "monto negativo": {"monto": Decimal("-5")},
            "tres decimales": {"monto": Decimal("1.505")},
            "float": {"monto": 18.1},
            "infinito": {"monto": Decimal("Infinity")},
            "demasiado grande": {"monto": Decimal("100000000")},
            "fecha futura": {"fecha": date(2026, 11, 21)},
            "fecha con hora": {"fecha": datetime(2026, 11, 20, 8, tzinfo=LIMA)},
            "descripcion larga": {"descripcion": "x" * 256},
        }
        for nombre, extra in casos.items():
            with self.subTest(nombre), self.assertRaises(DatosInvalidos):
                self._crear(**extra)
        self.assertFalse(Transaccion.objects.exists())

    def test_categoria_de_otro_tipo_o_ajena_no_se_acepta(self):
        from .servicios import OpcionInvalida

        ajena = Categoria.objects.create(nombre="Secreta", usuario=self.otro, tipo="ingreso")
        for nombre, extra in {"gasto con InDrive": {"tipo": "gasto"},
                              "ingreso con Comida": {"categoria_id": self.comida.pk},
                              "ajena": {"categoria_id": ajena.pk}}.items():
            with self.subTest(nombre), self.assertRaises(OpcionInvalida):
                self._crear(**extra)

    def test_editar_todo_en_un_movimiento_del_panel(self):
        from datetime import date

        t = self._crear()
        self._editar(t, tipo="gasto", monto=Decimal("12.5"), categoria_id=self.comida.pk,
                     fecha=date(2026, 11, 19), descripcion="Almuerzo")
        t.refresh_from_db()
        self.assertEqual((t.tipo, t.monto, t.categoria, t.descripcion),
                         ("gasto", Decimal("12.50"), self.comida, "Almuerzo"))
        # Cambió el día, conserva la hora que tenía
        self.assertEqual(t.fecha_hora, datetime(2026, 11, 19, 21, 15, tzinfo=LIMA))

    def test_cambiar_de_tipo_sin_categoria_nueva_la_quita(self):
        t = self._crear()
        self._editar(t, tipo="gasto")
        t.refresh_from_db()
        self.assertIsNone(t.categoria)  # InDrive no puede quedar en un gasto

    def test_mover_a_hoy_una_hora_que_aun_no_llega_queda_en_ahora(self):
        from datetime import date

        t = self._crear(fecha=date(2026, 11, 18))  # mediodía del 18
        temprano = datetime(2026, 11, 20, 9, 0, tzinfo=LIMA)
        self._editar(t, ahora=temprano, fecha=date(2026, 11, 20))
        t.refresh_from_db()
        self.assertEqual(t.fecha_hora, temprano)

    def test_en_un_yape_solo_categoria_y_descripcion(self):
        from datetime import date

        from .servicios import DatosInvalidos

        yape = Transaccion.objects.create(
            usuario=self.u, tipo="gasto", monto=Decimal("18.50"), contraparte="Ana G.",
            fecha_hora=datetime(2026, 11, 20, 9, 0, tzinfo=LIMA), fuente="yape",
            numero_operacion="1")
        # Mandar los mismos valores (formulario completo) sí se acepta
        self._editar(yape, tipo="gasto", monto=Decimal("18.50"), fecha=date(2026, 11, 20),
                     categoria_id=self.comida.pk, descripcion="Menú")
        yape.refresh_from_db()
        self.assertEqual((yape.categoria, yape.descripcion), (self.comida, "Menú"))
        # ...y la regla aprendida se actualiza, igual que desde WhatsApp
        self.assertEqual(ReglaCategoria.objects.get(contraparte="ana g.").categoria, self.comida)

        for campo, valor in {"monto": Decimal("20.00"), "tipo": "ingreso",
                             "fecha": date(2026, 11, 19)}.items():
            with self.subTest(campo), self.assertRaises(DatosInvalidos) as e:
                self._editar(yape, **{campo: valor})
            self.assertEqual(e.exception.campo, f"{campo}_no_editable")

    def test_no_se_edita_lo_ajeno_ni_campos_desconocidos(self):
        from .servicios import DatosInvalidos, OpcionInvalida, editar_movimiento_panel

        t = self._crear()
        with self.assertRaises(OpcionInvalida):
            editar_movimiento_panel(self.otro, t.pk, {"monto": Decimal("1.00")})
        with self.assertRaises(DatosInvalidos):
            self._editar(t, usuario_id=self.otro.pk)

    def test_ingresos_no_crean_reglas(self):
        from .servicios import asignar_categoria

        yape = Transaccion.objects.create(
            usuario=self.u, tipo="ingreso", monto=Decimal("150.00"), contraparte="Maria L.",
            fecha_hora=self.AHORA, fuente="yape", numero_operacion="2")
        asignar_categoria(self.u, yape.pk, self.indrive.pk)
        yape.refresh_from_db()
        self.assertEqual(yape.categoria, self.indrive)
        self.assertFalse(ReglaCategoria.objects.exists())
