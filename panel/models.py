from django.db import models

from finanzas.models import Usuario


class TokenAcceso(models.Model):
    """Un enlace mágico de un solo uso para entrar al panel.

    Guardamos el HASH del token, nunca el token: si alguien lee la BD (o un
    respaldo), no puede armar un enlace válido con lo que encuentra ahí.
    """

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="tokens_acceso")
    token_hash = models.CharField(max_length=64, unique=True)  # sha256 en hexadecimal
    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField()
    usado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "token de acceso"
        verbose_name_plural = "tokens de acceso"
        ordering = ["-creado_en"]

    def __str__(self):
        estado = "usado" if self.usado_en else "pendiente"
        return f"{self.usuario} · {estado} · {self.creado_en:%d/%m %H:%M}"
