"""Decifra um backup gerado pelo backup_cifrado (risco R04).

Só devolve o SQL. Não grava em banco nenhum de propósito: a importação é feita
à mão, num MySQL local, como manda o roteiro de docs/continuidade.md.
"""

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from config.backup import BackupInvalido, decifrar_backup, ler_chave


class Command(BaseCommand):
    help = "Decifra um backup .sql.enc com a BACKUP_KEY e grava o SQL."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--saida", help="Arquivo .sql de destino (padrão: mesmo nome, sem .enc).")

    def handle(self, *args, arquivo, saida, **options):
        origem = Path(arquivo)
        if not origem.is_file():
            raise CommandError(f"Arquivo não encontrado: {origem}")

        try:
            dados = decifrar_backup(origem.read_bytes(), ler_chave(os.environ.get("BACKUP_KEY")))
        except BackupInvalido as erro:
            raise CommandError(str(erro)) from erro

        destino = Path(saida) if saida else origem.with_suffix("")
        destino.write_bytes(dados)
        self.stdout.write(self.style.WARNING(
            f"SQL gravado em {destino}. Ele tem dados pessoais em texto puro: "
            "apague o arquivo assim que terminar o teste de restauração."
        ))
