"""Gera um backup cifrado do banco (risco R04). Veja docs/continuidade.md."""

import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from config.backup import (
    BackupInvalido,
    argumentos_do_mysqldump,
    arquivo_de_opcoes,
    cifrar_backup,
    ler_chave,
)


class Command(BaseCommand):
    help = "Copia o banco com o mysqldump e grava o resultado cifrado com a BACKUP_KEY."

    def add_arguments(self, parser):
        parser.add_argument("--saida", help="Arquivo de destino (padrão: backups/<data>.sql.enc).")
        parser.add_argument(
            "--mysqldump",
            default=os.environ.get("MYSQLDUMP", "mysqldump"),
            help="Caminho do mysqldump, se ele não estiver no PATH.",
        )

    def handle(self, *args, saida, mysqldump, **options):
        banco = settings.DATABASES["default"]
        if "mysql" not in banco["ENGINE"]:
            raise CommandError("O backup é do MySQL. O banco configurado não é MySQL.")

        try:
            chave = ler_chave(os.environ.get("BACKUP_KEY"))
        except BackupInvalido as erro:
            raise CommandError(str(erro)) from erro

        with arquivo_de_opcoes(banco) as opcoes:
            try:
                resultado = subprocess.run(
                    argumentos_do_mysqldump(banco, opcoes, mysqldump),
                    capture_output=True,
                    check=False,
                )
            except FileNotFoundError as erro:
                raise CommandError(f"mysqldump não encontrado: {mysqldump}") from erro

        if resultado.returncode != 0 or not resultado.stdout:
            erro = resultado.stderr.decode("utf-8", "replace").strip()
            raise CommandError(f"O mysqldump falhou: {erro}")

        destino = Path(saida or f"backups/health-in-sight-{timezone.now():%Y%m%d-%H%M}.sql.enc")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(cifrar_backup(resultado.stdout, chave))

        self.stdout.write(self.style.SUCCESS(
            f"Backup cifrado gravado em {destino} ({destino.stat().st_size // 1024} KB). "
            "Guarde-o fora do Aiven, longe da BACKUP_KEY."
        ))
