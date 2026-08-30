""""Configuração do algoritmo de hash de senha Argon2 para o projeto."""

""""requisito 1.2: Algoritmo de hash de senha seguro (Argon2)"""

from django.contrib.auth.hashers import Argon2PasswordHasher


class ProjectArgon2PasswordHasher(Argon2PasswordHasher):

    # Nome do algoritmo. É o prefixo que aparece no início da string gravada.
    algorithm = "argon2"

    # Número de passagens sobre a memória. Multiplica o tempo de cálculo.
    # Compensa o custo de memória menor desta configuração da RFC.
    time_cost = 3

    # Memória exigida por cálculo, em KiB. 65536 KiB = 64 MiB.
    # É o parâmetro que mais protege: uma GPU tem milhares de núcleos, mas
    # pouca memória por núcleo. Exigir 64 MiB por hash impede que ela calcule
    # milhares em paralelo, que é como ataques de força bruta ganham escala.
    # Vale notar que esta é memória de processamento, transitória. No banco,
    # cada senha ocupa cerca de 100 bytes.
    memory_cost = 65536

    # Número de threads processadas em paralelo, compatível com os núcleos
    # disponíveis no servidor de aplicação.
    parallelism = 2
