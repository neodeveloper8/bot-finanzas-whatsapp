"""Decide QUÉ hacer con cada mensaje entrante (rápido, dentro del webhook).

Las reglas que deben cumplirse SIEMPRE y al instante (lista blanca,
deduplicación) se quedan aquí. Lo lento se encola para el worker.
"""
import logging
from collections.abc import Iterator

from django.conf import settings
from django.db import IntegrityError, transaction
from django_q.tasks import async_task

from .models import MensajeProcesado

logger = logging.getLogger(__name__)


def extraer_mensajes(payload: dict) -> Iterator[tuple[dict, str]]:
    """Recorre la estructura anidada de Meta y devuelve (mensaje, nombre_de_perfil).

    Usamos .get(..., []) en cada nivel porque los avisos de estado
    ("entregado", "leído") llegan por el mismo webhook SIN la clave "messages".
    El nombre viene aparte, en "contacts", emparejado por wa_id.
    """
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            nombres = {
                c.get("wa_id"): c.get("profile", {}).get("name", "")
                for c in value.get("contacts", [])
            }
            for mensaje in value.get("messages", []):
                yield mensaje, nombres.get(mensaje.get("from"), "")


def procesar_mensaje(mensaje: dict, nombre_perfil: str = "") -> None:
    remitente = mensaje.get("from", "")
    wamid = mensaje.get("id", "")

    # 1) Lista blanca: si no eres tú, se ignora sin responder ni guardar nada
    if remitente not in settings.WHATSAPP_NUMEROS_PERMITIDOS:
        logger.warning("Mensaje de número no permitido (%s): ignorado", remitente)
        return

    # 2) Deduplicación: el UNIQUE de la BD decide si ya lo vimos.
    # atomic() crea un "savepoint": si el INSERT falla, solo se deshace ese
    # INSERT y la conexión sigue usable para lo que venga después.
    try:
        with transaction.atomic():
            MensajeProcesado.objects.create(
                wamid=wamid, remitente=remitente, tipo=mensaje.get("type", "")
            )
    except IntegrityError:
        logger.info("Mensaje duplicado (%s): ignorado", wamid)
        return

    # 3) Encolar: el worker hará el trabajo lento. Pasamos la ruta como texto
    # para que el worker importe la función por su cuenta.
    async_task("whatsapp.tareas.atender_mensaje", mensaje, nombre_perfil)
    logger.info("Mensaje %s encolado", wamid)
