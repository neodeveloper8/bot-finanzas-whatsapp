from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST

from .demo import usuario_demo
from .servicios import canjear_token, token_es_valido
from .sesion import es_demo, iniciar_sesion, iniciar_sesion_demo, panel_requerido, usuario_de_la_sesion

# 410 Gone: "esto existió pero ya no está". Más honesto que un 404 para un enlace vencido.
VENCIDO = 410


def _sin_indexar(respuesta, extra: str = ""):
    """Cabecera para buscadores: además del <meta noindex> de las plantillas,
    cubre respuestas sin HTML (como un redirect)."""
    respuesta["X-Robots-Tag"] = f"noindex{extra}"
    return respuesta


@never_cache
@require_http_methods(["GET", "POST"])
def entrar(request, token):
    """GET muestra un botón; solo el POST gasta el token.

    ¿Por qué no entrar directo con el GET? Porque hay programas que abren los
    links solos para generar la vista previa (WhatsApp, antivirus, filtros de
    correo). Si el GET gastara el token, ese robot lo quemaría antes que tú.
    Los robots hacen GET, pero no envían formularios.
    """
    if request.method == "POST":
        usuario = canjear_token(token)
        if usuario is None:
            return render(request, "panel/acceso.html", {"motivo": "vencido"}, status=VENCIDO)
        iniciar_sesion(request, usuario)
        # Redirigir saca el token de la barra de direcciones (y del botón "atrás")
        return redirect("panel:inicio")

    if not token_es_valido(token):
        return render(request, "panel/acceso.html", {"motivo": "vencido"}, status=VENCIDO)
    return render(request, "panel/entrar.html", {"dias": settings.PANEL_SESION_DIAS})


def acceso(request):
    """Adónde va quien llega sin sesión: le explica cómo pedir su enlace."""
    motivo = "salio" if request.GET.get("salio") else "sin_sesion"
    return render(request, "panel/acceso.html", {"motivo": motivo})


@never_cache
@ensure_csrf_cookie  # deja la cookie csrftoken para que React la lea en sus POST/DELETE
@panel_requerido
def inicio(request):
    """Entrega la app de React. A partir de aquí, React habla con la API."""
    return _sin_indexar(render(request, "panel/app.html", {
        "datos_iniciales": {"nombre": request.usuario_panel.nombre, "es_demo": request.es_demo},
    }))


@never_cache
@require_http_methods(["GET", "HEAD"])
def demo(request):
    """Entra al panel como el usuario de la demo: datos ficticios y solo lectura.

    Si este navegador ya tiene una sesión REAL, no la tocamos: alguien podría
    mandarte este link y sacarte de tu panel. Para ver la demo, usa incógnito.
    """
    if not settings.PANEL_DEMO_ACTIVO:
        raise Http404
    if usuario_de_la_sesion(request) is None or es_demo(request):
        iniciar_sesion_demo(request, usuario_demo())
    return _sin_indexar(redirect("panel:inicio"), ", nofollow")


@require_POST
def salir(request):
    """Cierra la sesión en ESTE dispositivo. POST (con CSRF) para que un link
    malicioso con <img src=".../salir/"> no pueda cerrarte la sesión."""
    request.session.flush()
    return redirect(reverse("panel:acceso") + "?salio=1")
