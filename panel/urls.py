from django.urls import path

from . import api, views

app_name = "panel"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/<str:token>/", views.entrar, name="entrar"),
    path("acceso/", views.acceso, name="acceso"),
    path("salir/", views.salir, name="salir"),
    path("demo/", views.demo, name="demo"),
    # API JSON (la consume React)
    path("api/resumen/", api.resumen, name="api_resumen"),
    path("api/movimientos/", api.movimientos, name="api_movimientos"),
    path("api/movimientos/<int:transaccion_id>/", api.movimiento, name="api_movimiento"),
    path("api/movimientos/<int:transaccion_id>/categoria/", api.cambiar_categoria,
         name="api_cambiar_categoria"),
    path("api/categorias/", api.categorias, name="api_categorias"),
]
