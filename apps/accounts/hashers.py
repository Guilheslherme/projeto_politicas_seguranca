"""
Hasher de senhas do projeto - requisitos 1.1 a 1.4.

Argon2id: recomendado pela RFC 9106 e pelo OWASP Password Storage Cheat Sheet.

Parametros (segunda configuracao recomendada pela RFC 9106, secao 4, para
ambientes com memoria limitada):

    m = 65536 KiB (64 MiB)
    t = 3 iteracoes
    p = 2 lanes

O padrao do Django (m=102400 KiB, t=2, p=8) consome cerca de 100 MiB por hash.
A instancia gratuita do Render tem 512 MB de RAM no total.
"""

from django.contrib.auth.hashers import Argon2PasswordHasher


class ProjectArgon2PasswordHasher(Argon2PasswordHasher):
    algorithm = "argon2"

    time_cost = 3
    memory_cost = 65536
    parallelism = 2