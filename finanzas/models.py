from django.db import models
from django.db.models import Q


class Usuario(models.Model):
    """Una persona que usa el bot, identificada por su número de WhatsApp.

    Hoy eres solo tú, pero cada transacción cuelga de un Usuario desde el inicio:
    agregar esta FK más adelante, con datos ya cargados, sería mucho más caro.
    """

    telefono_wa = models.CharField(
        max_length=20, unique=True, help_text="Formato de Meta: 51 + 9 dígitos, sin '+'"
    )
    nombre = models.CharField(max_length=100, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    # Cada sesión del panel guarda el número vigente al entrar. El comando "salir"
    # lo incrementa y así invalida de golpe las sesiones de TODOS los dispositivos.
    sesion_version = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.nombre or self.telefono_wa


class TipoMovimiento(models.TextChoices):
    """Gasto o ingreso. Lo comparten Categoria y Transaccion (por eso vive afuera)."""

    GASTO = "gasto", "Gasto"
    INGRESO = "ingreso", "Ingreso"


class Categoria(models.Model):
    """Categorías de gasto o de ingreso. usuario=NULL significa del sistema (para todos).

    `tipo` separa "Comida" (gasto) de "InDrive" (ingreso): un gasto solo puede
    llevar una categoría de gasto y un ingreso una de ingreso. La BD no puede
    comprobar eso entre dos tablas; lo valida finanzas/servicios.py.
    """

    nombre = models.CharField(max_length=50)
    emoji = models.CharField(max_length=8, blank=True)
    tipo = models.CharField(
        max_length=10, choices=TipoMovimiento.choices, default=TipoMovimiento.GASTO
    )
    usuario = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.CASCADE, related_name="categorias"
    )

    class Meta:
        ordering = ["nombre"]
        constraints = [
            # Dos restricciones porque en SQL NULL != NULL: un unique (usuario, nombre)
            # normal permitiría dos categorías del sistema llamadas igual.
            models.UniqueConstraint(
                fields=["nombre"],
                condition=Q(usuario__isnull=True),
                name="categoria_sistema_nombre_unico",
            ),
            models.UniqueConstraint(
                fields=["usuario", "nombre"],
                condition=Q(usuario__isnull=False),
                name="categoria_usuario_nombre_unico",
            ),
        ]

    def __str__(self):
        return f"{self.emoji} {self.nombre}".strip()


class Transaccion(models.Model):
    Tipo = TipoMovimiento  # alias: el resto del código sigue usando Transaccion.Tipo.GASTO

    class Fuente(models.TextChoices):
        YAPE = "yape", "Yape"
        TEXTO = "texto", "Texto"
        VOZ = "voz", "Voz"
        PANEL = "panel", "Panel"  # cargado a mano desde el panel web

    usuario = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="transacciones"
    )  # PROTECT: borrar un usuario con historial debe ser una decisión explícita
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    monto = models.DecimalField(max_digits=10, decimal_places=2)  # Decimal: nunca float para dinero
    moneda = models.CharField(max_length=3, default="PEN")
    fecha_hora = models.DateTimeField(help_text="Cuándo ocurrió el pago (no cuándo se registró)")

    # A quién le pagaste (Yape) vs. qué compraste (texto/voz): son datos distintos
    contraparte = models.CharField(max_length=100, blank=True)
    contraparte_celular3 = models.CharField(max_length=3, blank=True)
    descripcion = models.CharField(max_length=255, blank=True)

    categoria = models.ForeignKey(
        Categoria, null=True, blank=True, on_delete=models.SET_NULL, related_name="transacciones"
    )
    fuente = models.CharField(max_length=10, choices=Fuente.choices)
    numero_operacion = models.CharField(max_length=30, null=True, blank=True)
    wamid_origen = models.CharField(
        max_length=255, blank=True, help_text="Mensaje de WhatsApp que creó esta transacción"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_hora"]
        verbose_name = "transacción"
        verbose_name_plural = "transacciones"
        constraints = [
            # Candado anti-duplicados: la misma operación de Yape no entra dos veces.
            # condition=...isnull=False -> los gastos de texto/voz (sin número) no chocan.
            models.UniqueConstraint(
                fields=["usuario", "fuente", "numero_operacion"],
                condition=Q(numero_operacion__isnull=False),
                name="transaccion_operacion_unica",
            ),
            models.CheckConstraint(condition=Q(monto__gt=0), name="transaccion_monto_positivo"),
            # Un Yape SIEMPRE trae número de operación; si falta, algo salió mal
            models.CheckConstraint(
                condition=~Q(fuente="yape") | Q(numero_operacion__isnull=False),
                name="transaccion_yape_requiere_operacion",
            ),
        ]
        indexes = [models.Index(fields=["usuario", "fecha_hora"])]  # para los resúmenes por fecha

    def __str__(self):
        signo = "-" if self.tipo == self.Tipo.GASTO else "+"
        quien = self.contraparte or self.descripcion
        return f"{signo}S/ {self.monto} {quien} ({self.fecha_hora:%d/%m %H:%M})"


class ReglaCategoria(models.Model):
    """Lo que el bot "aprendió": a esta contraparte le pones esta categoría.

    La clave es (contraparte normalizada + 3 últimos dígitos del celular)
    porque Yape enmascara los nombres: dos "Juan Per*" pueden ser personas
    distintas, y el celular las separa.
    """

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="reglas")
    contraparte = models.CharField(max_length=100, help_text="Normalizada: minúsculas, sin espacios extra")
    contraparte_celular3 = models.CharField(max_length=3, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="reglas")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "regla de categoría"
        verbose_name_plural = "reglas de categoría"
        constraints = [
            # Una sola regla por contraparte: corregir ACTUALIZA, no agrega otra
            models.UniqueConstraint(
                fields=["usuario", "contraparte", "contraparte_celular3"],
                name="regla_contraparte_unica",
            ),
        ]

    def __str__(self):
        return f"{self.contraparte} ({self.contraparte_celular3 or '???'}) → {self.categoria}"
