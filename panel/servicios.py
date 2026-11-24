"""Lógica del acceso al panel: crear enlaces, canjearlos y cerrar sesiones."""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from finanzas.models import Usuario

from .models import TokenAcceso

# Los tokens usados se guardan un tiempo como historial ("¿cuándo entré?") y luego se borran
CONSERVAR_HISTORIAL = timedelta(days=30)


def _hash(token: str) -> str:
    """sha256 a secas, sin sal ni algoritmo lento (a diferencia de una contraseña).

    Las contraseñas necesitan hashes lentos porque las personas eligen claves
    adivinables. Este token son 32 bytes al azar (256 bits): no hay diccionario
    que lo adivine. Y necesitamos que el hash sea determinista para BUSCARLO.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def crear_enlace(usuario: Usuario) -> str:
    """Genera un enlace nuevo y devuelve la URL completa para mandarla por WhatsApp."""
    ahora = timezone.now()
    token = secrets.token_urlsafe(32)  # aleatorio criptográfico; random NO sirve para esto

    with transaction.atomic():
        # Pedir un enlace nuevo anula los anteriores que no usaste: solo vale el último
        TokenAcceso.objects.filter(usuario=usuario, usado_en__isnull=True).delete()
        # Limpieza de paso, para que la tabla no crezca para siempre
        TokenAcceso.objects.filter(creado_en__lt=ahora - CONSERVAR_HISTORIAL).delete()
        TokenAcceso.objects.create(
            usuario=usuario,
            token_hash=_hash(token),
            expira_en=ahora + timedelta(minutes=settings.PANEL_ENLACE_MINUTOS),
        )

    return settings.PANEL_URL_BASE + reverse("panel:entrar", args=[token])


def _vigentes(token: str):
    return TokenAcceso.objects.filter(
        token_hash=_hash(token),
        usado_en__isnull=True,
        expira_en__gt=timezone.now(),
        usuario__activo=True,
    )


def token_es_valido(token: str) -> bool:
    """Solo consulta, NO gasta el token (para la pantalla con el botón "Entrar")."""
    return _vigentes(token).exists()


def canjear_token(token: str) -> Usuario | None:
    """Gasta el token y devuelve su usuario, o None si no sirve.

    El UPDATE condicional es el candado: "márcalo usado SOLO si sigue sin usar".
    Si dos peticiones llegan a la vez, la BD ejecuta los dos UPDATE en orden y
    solo el primero encuentra la fila sin usar (filas_afectadas == 1).
    Hacerlo en dos pasos (leer, revisar en Python, guardar) dejaría una ventana
    en la que ambas peticiones ven "sin usar" y las dos entran.
    """
    h = _hash(token)
    filas_afectadas = _vigentes(token).update(usado_en=timezone.now())
    if filas_afectadas != 1:
        return None
    return TokenAcceso.objects.select_related("usuario").get(token_hash=h).usuario


def cerrar_sesiones(usuario: Usuario) -> None:
    """Invalida TODAS las sesiones del panel de este usuario (comando "salir")."""
    with transaction.atomic():
        # F(): el +1 lo hace la BD, no Python. Sin carreras si llegan dos "salir" juntos.
        Usuario.objects.filter(pk=usuario.pk).update(sesion_version=F("sesion_version") + 1)
        TokenAcceso.objects.filter(usuario=usuario, usado_en__isnull=True).delete()
