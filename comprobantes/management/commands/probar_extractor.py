"""Reemplazo del viejo script de la Fase 1.

Uso:  python manage.py probar_extractor muestras/*
"""
from pathlib import Path

import anthropic
from django.core.management.base import BaseCommand
from pydantic import ValidationError

from comprobantes.extractor import detectar_media_type, extraer


class Command(BaseCommand):
    help = "Corre el extractor sobre imágenes locales y muestra el resultado."

    def add_arguments(self, parser):
        parser.add_argument("rutas", nargs="+", type=Path)

    def handle(self, *args, rutas, **options):
        for ruta in rutas:
            datos = ruta.read_bytes()
            media_type = detectar_media_type(datos)
            if media_type is None:
                self.stdout.write(f"\n(omitido, no es una imagen soportada: {ruta.name})")
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {ruta.name} ({media_type}) ==="))
            try:
                comprobante, uso = extraer(datos, media_type)
                self.stdout.write(comprobante.model_dump_json(indent=2))
                self.stdout.write(f"tokens -> entrada: {uso.input_tokens} | salida: {uso.output_tokens}")
            except ValidationError as e:
                self.stdout.write(self.style.ERROR(f"La IA devolvió datos inválidos:\n{e}"))
            except anthropic.APIError as e:
                self.stdout.write(self.style.ERROR(f"Error de la API: {e}"))
