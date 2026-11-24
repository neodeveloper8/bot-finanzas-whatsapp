from django.db import models


class MensajeProcesado(models.Model):
    """Registro de mensajes ya atendidos, para no procesar dos veces.

    Meta reintenta la entrega si no le respondemos a tiempo, así que el mismo
    mensaje (mismo wamid) puede llegar más de una vez. El UNIQUE de la BD es el
    candado: el segundo INSERT falla y sabemos que es un duplicado.
    """

    wamid = models.CharField(max_length=255, unique=True)
    remitente = models.CharField(max_length=20)
    tipo = models.CharField(max_length=20)
    recibido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mensaje procesado"
        verbose_name_plural = "mensajes procesados"
        ordering = ["-recibido_en"]

    def __str__(self):
        return f"{self.tipo} de {self.remitente} ({self.recibido_en:%d/%m %H:%M})"
