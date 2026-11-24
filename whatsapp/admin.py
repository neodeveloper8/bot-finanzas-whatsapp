from django.contrib import admin

from .models import MensajeProcesado


@admin.register(MensajeProcesado)
class MensajeProcesadoAdmin(admin.ModelAdmin):
    list_display = ("recibido_en", "remitente", "tipo", "wamid")
    list_filter = ("tipo",)
    search_fields = ("wamid", "remitente")
