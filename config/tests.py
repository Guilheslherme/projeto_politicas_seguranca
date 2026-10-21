"""Testes da conexão cifrada com o banco (risco R09)."""

import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

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
