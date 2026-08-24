"""Configuracoes usadas no servidor (Render)."""

from .base import *  # noqa: F403

DEBUG = False

ALLOWED_HOSTS = []

# Requisitos 3.1 e 3.2: comunicacao protegida e bloqueio de conexao insegura.

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# WhiteNoise comprime os arquivos estaticos e adiciona um hash ao nome,
# permitindo cache longo no navegador sem risco de servir versao antiga.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}