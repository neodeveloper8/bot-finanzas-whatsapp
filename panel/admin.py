from django.contrib import admin

from .models import TokenAcceso


@admin.register(TokenAcceso)
class TokenAccesoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "creado_en", "expira_en", "usado_en")
    list_filter = ("usado_en",)
    # Solo lectura: los tokens los crea el bot, no se editan a mano
    readonly_fields = ("usuario", "token_hash", "creado_en", "expira_en", "usado_en")

    def has_add_permission(self, request):
        return False
