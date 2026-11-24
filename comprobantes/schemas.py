"""Esquema de datos que extraemos de un comprobante de Yape."""
from datetime import date, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

CAMPOS_OBLIGATORIOS = ("monto", "contraparte", "fecha", "hora", "numero_operacion")


class ComprobanteYape(BaseModel):
    tipo: Literal["enviado", "recibido", "no_es_comprobante"]
    monto: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    contraparte: str | None = None  # "Juan Per*" tal cual, con asterisco
    celular_ultimos3: str | None = Field(default=None, pattern=r"^\d{3}$")
    fecha: date | None = None  # 2026-11-12
    hora: time | None = None  # 14:29 (24h)
    mensaje: str | None = None  # "Pan" o None
    destino: str | None = None  # "Yape", "Plin", etc.
    numero_operacion: str | None = Field(default=None, pattern=r"^\d+$")  # str: conserva ceros

    @model_validator(mode="after")
    def exigir_campos_si_es_comprobante(self):
        """Si NO es comprobante, todo puede venir vacío. Si lo es, los campos clave son obligatorios."""
        if self.tipo == "no_es_comprobante":
            return self
        faltantes = [c for c in CAMPOS_OBLIGATORIOS if getattr(self, c) is None]
        if faltantes:
            raise ValueError(f"Comprobante incompleto, faltan: {faltantes}")
        return self


# ---------------------------------------------------------------------------
# Gastos e ingresos escritos ("gasté 2.50 en papitas")
# ---------------------------------------------------------------------------
MAX_MOVIMIENTOS_POR_MENSAJE = 5


class MovimientoTexto(BaseModel):
    tipo: Literal["gasto", "ingreso"]
    monto: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    descripcion: str = Field(min_length=1, max_length=100)  # "Papitas", "Taxi a casa"
    categoria: str | None = None  # nombre de una categoría existente, de gasto o de ingreso
    # La IA dice HACE CUÁNTOS DÍAS; la fecha la calcula Python (sabe qué día es en Lima)
    dias_atras: int = Field(default=0, ge=0, le=31)


class InterpretacionTexto(BaseModel):
    """Lo que la IA entendió de un mensaje escrito.

    clase:
      - movimientos: encontró entre 1 y 5 gastos/ingresos en soles
      - no_es_movimiento: charla, saludos, preguntas ("jaja ok", "qué tal")
      - otra_moneda: habla de dólares, euros... (por ahora solo soles)
      - demasiados: más de 5 movimientos en un solo mensaje
    """

    clase: Literal["movimientos", "no_es_movimiento", "otra_moneda", "demasiados"]
    movimientos: list[MovimientoTexto] = Field(
        default_factory=list, max_length=MAX_MOVIMIENTOS_POR_MENSAJE
    )

    @model_validator(mode="before")
    @classmethod
    def descartar_lista_si_no_aplica(cls, datos):
        # mode="before": corre ANTES de validar campos. Si la IA dice "demasiados"
        # y manda 6 items, max_length=5 fallaría; aquí los descartamos primero.
        if isinstance(datos, dict) and datos.get("clase") != "movimientos":
            datos = {**datos, "movimientos": []}
        return datos

    @model_validator(mode="after")
    def exigir_movimientos(self):
        if self.clase == "movimientos" and not self.movimientos:
            raise ValueError("clase='movimientos' pero la lista está vacía")
        return self
