from django.contrib import admin

from .models import Categoria, ReglaCategoria, Transaccion, Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("telefono_wa", "nombre", "activo", "creado_en")


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("__str__", "tipo", "usuario")
    list_filter = ("tipo", "usuario")


@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    list_display = ("fecha_hora", "tipo", "monto", "contraparte", "descripcion", "categoria", "fuente")
    list_filter = ("tipo", "fuente", "categoria")
    search_fields = ("contraparte", "descripcion", "numero_operacion")
    date_hierarchy = "fecha_hora"


@admin.register(ReglaCategoria)
class ReglaCategoriaAdmin(admin.ModelAdmin):
    list_display = ("contraparte", "contraparte_celular3", "categoria", "usuario", "actualizado_en")
    list_filter = ("categoria",)
