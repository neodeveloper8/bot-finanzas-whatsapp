"""Programa las tareas de la demo en django-q2: regenerarla cada hora y limpiar sesiones a diario.

Va en una migración (y no en un paso manual) para que actualizar.sh la deje
lista en el servidor. Las tareas se guardan en la BD (tabla de django-q) y el
worker las ejecuta; se pueden ver y pausar en el admin, "Scheduled tasks".
"""
from datetime import timedelta

from django.db import migrations
from django.utils import timezone

TAREAS = [
    # (función, nombre en el admin, tipo de horario)
    ("panel.tareas.regenerar_demo", "Regenerar demo pública", "H"),  # H = cada hora
    ("panel.tareas.limpiar_sesiones", "Borrar sesiones vencidas", "D"),  # D = cada día
]


def _proxima_hora_en_punto():
    ahora = timezone.now()
    return ahora.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _proximas_4_30_de_lima():
    # 09:30 UTC = 04:30 en Lima (UTC-5 todo el año, sin horario de verano)
    ahora = timezone.now()
    siguiente = ahora.replace(hour=9, minute=30, second=0, microsecond=0)
    return siguiente if siguiente > ahora else siguiente + timedelta(days=1)


def programar(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    primeras = {"H": _proxima_hora_en_punto(), "D": _proximas_4_30_de_lima()}
    for func, nombre, tipo in TAREAS:
        # update_or_create por función: correr la migración otra vez no duplica tareas
        Schedule.objects.update_or_create(
            func=func,
            defaults={"name": nombre, "schedule_type": tipo, "repeats": -1, "next_run": primeras[tipo]},
        )


def desprogramar(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.filter(func__in=[f for f, _, _ in TAREAS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("panel", "0001_initial"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]
    operations = [migrations.RunPython(programar, desprogramar)]
