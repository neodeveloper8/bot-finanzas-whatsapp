"""Webhook de WhatsApp Cloud API.

GET  -> verificación inicial que hace Meta al registrar la URL.
POST -> Meta nos entrega eventos (mensajes entrantes, estados de entrega...).
"""
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .procesador import extraer_mensajes, procesar_mensaje

logger = logging.getLogger(__name__)


def _verificar_suscripcion(request) -> HttpResponse:
    """Meta manda hub.mode, hub.verify_token y hub.challenge.

    Si el token coincide con el nuestro, devolvemos el challenge tal cual:
    así Meta confirma que la URL es nuestra.
    """
    modo = request.GET.get("hub.mode")
    token = request.GET.get("hub.verify_token", "")
    challenge = request.GET.get("hub.challenge", "")

    if modo == "subscribe" and hmac.compare_digest(token, settings.WHATSAPP_VERIFY_TOKEN):
        logger.info("Webhook verificado por Meta")
        return HttpResponse(challenge, content_type="text/plain")

    logger.warning("Verificación rechazada (token incorrecto)")
    return HttpResponseForbidden()


def _firma_valida(request) -> bool:
    """Comprueba que el POST viene de Meta y no de cualquiera.

    Meta firma el cuerpo con HMAC-SHA256 usando el App Secret y manda la firma
    en el header X-Hub-Signature-256. Recalculamos y comparamos.
    """
    firma = request.headers.get("X-Hub-Signature-256", "")
    if not firma.startswith("sha256="):
        return False
    esperada = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode(), request.body, hashlib.sha256
    ).hexdigest()
    # compare_digest: comparación en tiempo constante (evita ataques de timing)
    return hmac.compare_digest(firma.removeprefix("sha256="), esperada)


@csrf_exempt  # Meta no manda token CSRF; nuestra protección es la firma HMAC
@require_http_methods(["GET", "POST"])
def webhook(request):
    if request.method == "GET":
        return _verificar_suscripcion(request)

    if not _firma_valida(request):
        logger.warning("POST con firma inválida: descartado")
        return HttpResponseForbidden()

    payload = json.loads(request.body)
    logger.debug("Evento recibido:\n%s", json.dumps(payload, indent=2, ensure_ascii=False))

    for mensaje, nombre_perfil in extraer_mensajes(payload):
        try:
            procesar_mensaje(mensaje, nombre_perfil)
        except Exception:
            # Nunca devolvemos 500 a Meta: si lo hacemos, reintenta el mismo
            # evento una y otra vez. Registramos el error y seguimos.
            logger.exception("Error procesando el mensaje %s", mensaje.get("id"))

    return HttpResponse(status=200)
