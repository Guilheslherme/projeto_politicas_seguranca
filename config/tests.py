"""Testes do banco: conexão cifrada (R09), rota de saúde e backup (R04)."""

import base64
import io
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.backup import (
    BackupInvalido,
    argumentos_do_mysqldump,
    arquivo_de_opcoes,
    cifrar_backup,
    decifrar_backup,
    ler_chave,
)
from config.banco import opcoes_de_tls


class TlsDoBancoTests(SimpleTestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.base = Path(pasta.name)
        (self.base / "certs").mkdir()
        (self.base / "certs" / "aiven-ca.pem").write_text("certificado")

    def test_com_certificado_confere_o_nome_do_servidor(self):
        # Antes, só o certificado era passado, sem conferir o nome do servidor.
        opcoes = opcoes_de_tls("certs/aiven-ca.pem", self.base, producao=True)

        self.assertEqual(opcoes["ssl_mode"], "VERIFY_IDENTITY")
        self.assertEqual(opcoes["ssl"], {"ca": str(self.base / "certs" / "aiven-ca.pem")})

    def test_producao_sem_certificado_nao_sobe(self):
        # Antes, a aplicação subia e conectava sem conferir o servidor.
        with self.assertRaises(ImproperlyConfigured):
            opcoes_de_tls("", self.base, producao=True)

    def test_producao_com_certificado_inexistente_nao_sobe(self):
        with self.assertRaises(ImproperlyConfigured):
            opcoes_de_tls("certs/outro.pem", self.base, producao=True)

    def test_desenvolvimento_sem_certificado_continua_funcionando(self):
        self.assertEqual(opcoes_de_tls("", self.base, producao=False), {})


class SaudeTests(TestCase):
    """Risco R04: rota para o monitor de disponibilidade."""

    def test_responde_ok_sem_expor_nada(self):
        resposta = self.client.get(reverse("saude"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})
        self.assertIn("no-store", resposta["Cache-Control"])

    def test_banco_fora_do_ar_responde_503_sem_a_mensagem_do_erro(self):
        with patch("config.saude.connection.cursor", side_effect=OperationalError("senha errada em host x")):
            resposta = self.client.get(reverse("saude"))

        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json(), {"status": "indisponivel"})


class BackupCifradoTests(SimpleTestCase):
    """Risco R04: backup do banco cifrado para guardar fora do Aiven."""

    BANCO = {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "defaultdb",
        "USER": "avnadmin",
        # Com aspas e barra invertida, que precisam de escape no arquivo de opções.
        "PASSWORD": r'se"nh\a-secreta',
        "HOST": "exemplo.aivencloud.com",
        "PORT": "12345",
        "OPTIONS": {"ssl": {"ca": "/certs/aiven-ca.pem"}, "ssl_mode": "VERIFY_IDENTITY"},
    }
    DUMP = b"INSERT INTO accounts_user VALUES (1,'pessoa@exemplo.com');"

    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.chave_texto = base64.urlsafe_b64encode(os.urandom(32)).decode()
        ambiente = patch.dict(os.environ, {"BACKUP_KEY": self.chave_texto})
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def test_backup_e_cifrado_e_volta_igual(self):
        cifrado = cifrar_backup(self.DUMP, ler_chave(self.chave_texto))

        self.assertNotIn(b"pessoa@exemplo.com", cifrado)
        self.assertEqual(decifrar_backup(cifrado, ler_chave(self.chave_texto)), self.DUMP)

    def test_chave_errada_ou_arquivo_alterado_e_recusado(self):
        cifrado = cifrar_backup(self.DUMP, ler_chave(self.chave_texto))

        with self.assertRaises(BackupInvalido):
            decifrar_backup(cifrado, os.urandom(32))
        with self.assertRaises(BackupInvalido):
            decifrar_backup(cifrado[:-1] + bytes([cifrado[-1] ^ 1]), ler_chave(self.chave_texto))

    def test_senha_nao_vai_na_linha_de_comando_e_o_tls_confere_o_servidor(self):
        with arquivo_de_opcoes(self.BANCO) as opcoes:
            argumentos = argumentos_do_mysqldump(self.BANCO, opcoes)
            conteudo = Path(opcoes).read_text(encoding="utf-8")

        self.assertFalse(any("senha" in a for a in argumentos))
        self.assertIn("--ssl-mode=VERIFY_IDENTITY", argumentos)
        self.assertIn(r'password="se\"nh\\a-secreta"', conteudo)
        self.assertFalse(Path(opcoes).exists())

    def test_comandos_de_backup_e_restauracao_fazem_o_caminho_completo(self):
        destino = self.pasta / "teste.sql.enc"
        processo = SimpleNamespace(returncode=0, stdout=self.DUMP, stderr=b"")
        with override_settings(DATABASES={"default": self.BANCO}), \
                patch("apps.accounts.management.commands.backup_cifrado.subprocess.run", return_value=processo):
            call_command("backup_cifrado", saida=str(destino), stdout=io.StringIO())

        self.assertNotIn(b"pessoa@exemplo.com", destino.read_bytes())
        call_command("restaurar_backup", str(destino), stdout=io.StringIO())
        self.assertEqual((self.pasta / "teste.sql").read_bytes(), self.DUMP)

    def test_sem_backup_key_o_backup_nao_roda(self):
        with patch.dict(os.environ, {"BACKUP_KEY": ""}), override_settings(DATABASES={"default": self.BANCO}):
            with self.assertRaises(CommandError):
                call_command("backup_cifrado", saida=str(self.pasta / "x.enc"), stdout=io.StringIO())
