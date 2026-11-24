"""Carga los datos ficticios de la demo pública del panel. No llama a ninguna API.

    python manage.py seed_demo            # solo si la demo aún no tiene datos
    python manage.py seed_demo --reset    # borra SOLO los movimientos de la demo y los regenera

En producción no hace falta correrlo a mano: una tarea programada de django-q2
(panel/tareas.py) lo hace cada hora. Las fechas son relativas a hoy y cada
reset agrega los movimientos de hoy que ya "pasaron".
"""
from django.core.management.base import BaseCommand, CommandError

from panel.demo import regenerar, usuario_demo


class Command(BaseCommand):
    help = "Crea o regenera los movimientos ficticios del usuario demo"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Borra los movimientos del usuario demo (y solo los suyos) y los regenera")

    def handle(self, *args, **opciones):
        try:
            resultado = regenerar(reset=opciones["reset"])
        except LookupError as e:
            raise CommandError(str(e))

        if resultado is None:
            self.stdout.write(self.style.WARNING(
                "La demo ya tiene movimientos. Usa --reset para regenerarlos."))
            return
        creados, borrados = resultado
        self.stdout.write(self.style.SUCCESS(
            f"Demo lista: {creados} movimientos (borrados {borrados}) para {usuario_demo().nombre}."))
