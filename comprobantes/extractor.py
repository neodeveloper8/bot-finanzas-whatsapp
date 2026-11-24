"""Imagen de comprobante -> ComprobanteYape validado (lógica de la Fase 1).

Ahora es un módulo reutilizable: lo llama la tarea en segundo plano del bot
y el comando `probar_extractor`. La API key se lee de ANTHROPIC_API_KEY,
que Django ya cargó desde .env.
"""
import base64

import anthropic

from .schemas import ComprobanteYape

MODELO = "claude-haiku-5-5"

PROMPT = """Eres un extractor de datos de comprobantes de Yape (Perú).
Analiza la imagen y llama a la herramienta `registrar_comprobante`.

Reglas:
- tipo: "¡Yapeaste!" -> "enviado". "¡Te Yapearon!" -> "recibido".
  Si la imagen NO es un comprobante de Yape -> "no_es_comprobante" y deja el resto en null.
- monto: texto con exactamente 2 decimales. "S/ 6" -> "6.00", "S/ 1.50" -> "1.50".
  Si hay separador de miles, quítalo: "S/ 1,250.50" -> "1250.50".
- contraparte: el nombre tal cual aparece, incluido el asterisco final.
- celular_ultimos3: solo los 3 dígitos visibles de "Nro. de celular".
- fecha: formato YYYY-MM-DD.
- hora: la que está junto al ícono de reloj del comprobante, en 24h (HH:MM).
  NO uses la hora de la barra de estado del celular (arriba de la pantalla).
- mensaje: el texto del recuadro de mensaje si existe; si no hay, null.
- numero_operacion: tal cual, conservando ceros a la izquierda.
- Ignora el código de seguridad, el banner decorativo y la publicidad.
- Nunca inventes un dato: si no se lee, usa null."""

_client = None


def _cliente() -> anthropic.Anthropic:
    """Crea el cliente la primera vez que se usa (no al importar el módulo).

    Así Django puede arrancar, migrar o correr tests sin tocar la API.
    """
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def detectar_media_type(datos: bytes) -> str | None:
    """Detecta el tipo REAL de imagen por sus primeros bytes ("magic bytes")."""
    if datos.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    if datos.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None


def _schema_para_tool() -> dict:
    schema = ComprobanteYape.model_json_schema()
    # monto como TEXTO para no pasar nunca por float
    schema["properties"]["monto"] = {
        "anyOf": [{"type": "string", "pattern": r"^\d+\.\d{2}$"}, {"type": "null"}],
        "description": "Monto con 2 decimales, como texto. Ej: '6.00'",
    }
    return schema


def extraer(datos: bytes, media_type: str) -> tuple[ComprobanteYape, anthropic.types.Usage]:
    respuesta = _cliente().messages.create(
        model=MODELO,
        max_tokens=1024,
        tools=[{
            "name": "registrar_comprobante",
            "description": "Registra los datos extraídos de un comprobante de Yape.",
            "input_schema": _schema_para_tool(),
        }],
        tool_choice={"type": "tool", "name": "registrar_comprobante"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(datos).decode(),
                }},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    bloque = next(b for b in respuesta.content if b.type == "tool_use")
    return ComprobanteYape.model_validate(bloque.input), respuesta.usage
