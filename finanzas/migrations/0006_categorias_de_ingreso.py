"""Carga las categorías de INGRESO del sistema (usuario=NULL).

Igual que 0002: en una migración de datos para que existan en todos los
entornos (tu laptop, los tests, el VPS) sin un paso manual al desplegar.
"""
from django.db import migrations

CATEGORIAS = [
    ("Sueldo", "💼"),
    ("InDrive", "🚗"),
    ("Otros ingresos", "💵"),
]


def crear(apps, schema_editor):
    Categoria = apps.get_model("finanzas", "Categoria")
    for nombre, emoji in CATEGORIAS:
        Categoria.objects.get_or_create(
            nombre=nombre, usuario=None, defaults={"emoji": emoji, "tipo": "ingreso"}
        )


def borrar(apps, schema_editor):
    Categoria = apps.get_model("finanzas", "Categoria")
    Categoria.objects.filter(usuario=None, nombre__in=[n for n, _ in CATEGORIAS]).delete()


class Migration(migrations.Migration):
    dependencies = [("finanzas", "0005_categoria_tipo_y_fuente_panel")]
    operations = [migrations.RunPython(crear, borrar)]
