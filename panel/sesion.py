"""Sesión del panel, separada del login del admin de Django.

No usamos django.contrib.auth (login/User) porque quien entra al panel es un
Usuario del bot (un número de WhatsApp), no un usuario del admin. Guardamos su
id en la sesión y listo. El admin sigue con su propio login, intacto.
"""
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect

from finanzas.models import Usuario

CLAVE_USUARIO = "panel_usuario_id"
CLAVE_VERSION = "panel_sesion_version"
CLAVE_DEMO = "panel_demo"
METODOS_DE_LECTURA = ("GET", "HEAD", "OPTIONS")


def _duracion() -> timedelta:
    return timedelta(days=settings.PANEL_SESION_DIAS)


def iniciar_sesion(request, usuario: Usuario) -> None:
    # cycle_key: nuevo id de sesión al entrar. Evita la "fijación de sesión":
    # que alguien te haga usar un id que él ya conoce y luego lo reutilice.
    request.session.cycle_key()
    request.session[CLAVE_USUARIO] = usuario.pk
    request.session[CLAVE_VERSION] = usuario.sesion_version
    # Solo ESTA sesión dura 30 días; la del admin conserva su duración por defecto
    request.session.set_expiry(_duracion())


def iniciar_sesion_demo(request, usuario: Usuario) -> None:
    """Como iniciar_sesion, pero marcada como demo: solo lectura y 2 horas FIJAS.

    La marca vive en la sesión (del lado del servidor), no en la cookie: el
    navegador no puede quitársela para escribir.
    """
    request.session.cycle_key()
    request.session[CLAVE_USUARIO] = usuario.pk
    request.session[CLAVE_VERSION] = usuario.sesion_version
    request.session[CLAVE_DEMO] = True
    request.session.set_expiry(timedelta(hours=settings.PANEL_DEMO_HORAS))


def es_demo(request) -> bool:
    return request.session.get(CLAVE_DEMO, False)


def usuario_de_la_sesion(request) -> Usuario | None:
    usuario_id = request.session.get(CLAVE_USUARIO)
    if usuario_id is None:
        return None
    usuario = Usuario.objects.filter(pk=usuario_id, activo=True).first()
    if usuario is None or request.session.get(CLAVE_VERSION) != usuario.sesion_version:
        # Usuario desactivado o usó "salir" desde WhatsApp: esta sesión ya no vale
        request.session.flush()
        return None
    return usuario


def _requerir_sesion(sin_sesion):
    """Fábrica de decoradores: lo único que cambia es qué responder sin sesión."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            usuario = usuario_de_la_sesion(request)
            if usuario is None:
                return sin_sesion()
            request.es_demo = es_demo(request)
            if request.es_demo:
                # La regla de solo lectura vive AQUÍ, no en los botones de React:
                # cubre toda vista protegida, incluidas las que se agreguen mañana.
                if request.method not in METODOS_DE_LECTURA:
                    return JsonResponse({"error": "demo_solo_lectura"}, status=403)
            else:
                request.session.set_expiry(_duracion())  # vencimiento deslizante (la demo no)
            request.usuario_panel = usuario
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


# Páginas: sin sesión te llevan a la pantalla de acceso
panel_requerido = _requerir_sesion(lambda: redirect("panel:acceso"))

# API: sin sesión responde 401 en JSON. Un redirect no le sirve a fetch():
# lo seguiría en silencio y React recibiría HTML donde esperaba JSON.
api_requerida = _requerir_sesion(
    lambda: JsonResponse({"error": "sin_sesion"}, status=401)
)
