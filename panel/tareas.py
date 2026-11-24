"""Tareas programadas del panel. Las corre el worker de django-q2 (botfin-worker).

Se programan con una migración (panel/migrations/0002_programar_tareas_demo.py),
así que llegan al servidor con actualizar.sh: no hace falta cron, que en el
servidor compartido no está disponible para botfin.
"""
import logging

from django.conf import settings
from django.core.management import call_command

from .demo import regenerar

logger = logging.getLogger(__name__)


def regenerar_demo() -> None:
    """Cada hora: pone al día los datos de la demo. Con la demo apagada no hace nada."""
    if not settings.PANEL_DEMO_ACTIVO:
        return
    creados, borrados = regenerar(reset=True)
    logger.info("Demo regenerada: %d movimientos (borrados %d)", creados, borrados)


def limpiar_sesiones() -> None:
    """Cada día: borra las sesiones vencidas (cada visita a la demo crea una)."""
    call_command("clearsessions")
    logger.info("Sesiones vencidas borradas")
