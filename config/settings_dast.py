"""Configuração usada só pelo teste dinâmico (OWASP ZAP) no GitHub Actions.

É a configuração de produção, com DJANGO_DEBUG=0: HTTPS obrigatório, cookies
seguros, HSTS, CSP, limite de tentativas e 2FA, do jeito que o site roda no
Render. Só duas coisas mudam, para o scan nunca encostar em nada real:

- o banco é um SQLite descartável, criado no runner a cada execução, e não o
  MySQL do Aiven;
- nenhum e-mail é enviado, mesmo que exista uma chave do Brevo no ambiente.
"""

from config.settings import *  # noqa: F401,F403
from config.settings import BASE_DIR

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dast.sqlite3",
    }
}

BREVO_API_KEY = ""
