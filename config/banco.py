"""TLS da conexão com o MySQL (risco R09).

Fica fora do settings.py para poder ser testado: o settings é lido uma vez só,
quando o Django sobe.
"""

from django.core.exceptions import ImproperlyConfigured


def opcoes_de_tls(ssl_ca, base_dir, producao):
    """Opções do driver para a conexão cifrada com o banco.

    Com o certificado da autoridade do Aiven (DB_SSL_CA), a conexão confere
    a cadeia do certificado e também o nome do servidor (VERIFY_IDENTITY).
    Só a cadeia não basta: qualquer servidor com certificado da mesma
    autoridade passaria, e a conexão poderia ser desviada para ele.

    Em produção, sem o certificado a aplicação não sobe. Antes ela subia e
    conectava com TLS sem conferir nada, o que abre caminho para um
    intermediário ler a senha do banco e os dados.
    """
    if not ssl_ca:
        if producao:
            raise ImproperlyConfigured(
                "DB_SSL_CA nao definido em producao: sem o certificado do banco, a "
                "conexao nao confere com quem esta falando."
            )
        return {}

    caminho = base_dir / ssl_ca
    if producao and not caminho.is_file():
        raise ImproperlyConfigured(f"Certificado do banco nao encontrado em {caminho}.")

    return {"ssl": {"ca": str(caminho)}, "ssl_mode": "VERIFY_IDENTITY"}
