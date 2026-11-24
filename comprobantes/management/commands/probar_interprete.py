"""Prueba el intérprete de texto sin WhatsApp (sí gasta tokens de la API).

    python manage.py probar_interprete "gasté 2.50 en papitas" "ayer 15 de almuerzo y 8 de taxi"
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from comprobantes.interprete import interpretar
from finanzas.models import Categoria
from finanzas.resumenes import DIAS
from finanzas.servicios import LIMA


class Command(BaseCommand):
    help = "Interpreta uno o más textos con la IA y muestra el resultado"

    def add_arguments(self, parser):
        parser.add_argument("textos", nargs="+")

    def handle(self, *args, **opciones):
        del_sistema = Categoria.objects.filter(usuario=None)
        gasto = list(del_sistema.filter(tipo="gasto").values_list("nombre", flat=True))
        ingreso = list(del_sistema.filter(tipo="ingreso").values_list("nombre", flat=True))
        dia = DIAS[timezone.localtime(timezone.now(), LIMA).weekday()]
        for texto in opciones["textos"]:
            r, uso = interpretar(texto, gasto, ingreso, dia)
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n«{texto}»"))
            self.stdout.write(f"  clase: {r.clase}  | tokens {uso.input_tokens}/{uso.output_tokens}")
            for m in r.movimientos:
                self.stdout.write(f"  - {m.tipo} S/ {m.monto} · {m.descripcion} "
                                  f"[{m.categoria}] hace {m.dias_atras} día(s)")
