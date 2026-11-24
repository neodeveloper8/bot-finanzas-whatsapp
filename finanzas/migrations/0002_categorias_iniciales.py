"""Carga las categorías del sistema (usuario=NULL).

Va en una migración de datos, no en un script aparte: así existen en
cualquier entorno (tu laptop, los tests, Railway) sin un paso manual.
"""
from django.db import migrations

CATEGORIAS = [
    ("Comida", "🍔"),
    ("Transporte", "🚕"),
    ("Compras", "🛒"),
    ("Hogar", "🏠"),
    ("Salud", "💊"),
    ("Entretenimiento", "🎉"),
    ("Familia", "👨‍👩‍👧"),
    ("Servicios", "📱"),
    ("Otros", "💸"),
]


def crear(apps, schema_editor):
    # apps.get_model (no import directo): usa el modelo tal como era EN ESTA migración
    Categoria = apps.get_model("finanzas", "Categoria")
    for nombre, emoji in CATEGORIAS:
        Categoria.objects.get_or_create(nombre=nombre, usuario=None, defaults={"emoji": emoji})


def borrar(apps, schema_editor):
    Categoria = apps.get_model("finanzas", "Categoria")
    Categoria.objects.filter(usuario=None, nombre__in=[n for n, _ in CATEGORIAS]).delete()


class Migration(migrations.Migration):
    dependencies = [("finanzas", "0001_initial")]
    operations = [migrations.RunPython(crear, borrar)]
