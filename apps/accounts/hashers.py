""""Criptografia de senhas com Argon2, com parâmetros customizados para maior segurança."""

from django.contrib.auth.hashers import Argon2PasswordHasher


class ProjectArgon2PasswordHasher(Argon2PasswordHasher):
    algorithm = "argon2"

    time_cost = 3
    memory_cost = 65536
    parallelism = 2