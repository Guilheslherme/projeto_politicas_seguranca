import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from axes.models import AccessAttempt
from axes.utils import reset

User = get_user_model()

SENHA = "TrocaEssaSenha2026"


def codigo_atual(device):
    """Gera o código que o aplicativo autenticador mostraria neste instante."""
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    totp.time = time.time()
    return f"{totp.token():06d}"


class ArmazenamentoDeSenhaTests(TestCase):
    """Requisitos 1.1, 1.2, 1.3 e 1.4."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="teste@exemplo.com",
            full_name="Usuario de Teste",
            password=SENHA,
        )

    def test_senha_nao_fica_em_texto_puro(self):
        self.assertNotEqual(self.user.password, SENHA)
        self.assertNotIn(SENHA, self.user.password)

    def test_hash_usa_argon2id(self):
        self.assertTrue(self.user.password.startswith("argon2$argon2id$"))

    def test_parametros_de_custo_sao_os_configurados(self):
        # 64 MiB de memória, 3 iterações e paralelismo 2, conforme a RFC 9106.
        self.assertIn("m=65536,t=3,p=2", self.user.password)

    def test_salt_e_unico_por_usuario(self):
        outro = User.objects.create_user(
            email="outro@exemplo.com",
            full_name="Outro Usuario",
            password=SENHA,
        )
        # Mesma senha, mesmos parâmetros, hashes diferentes.
        self.assertNotEqual(self.user.password, outro.password)

    def test_senha_continua_conferindo(self):
        self.assertTrue(self.user.check_password(SENHA))
        self.assertFalse(self.user.check_password("qualquer outra"))


class DuasEtapasTests(TestCase):
    """Requisitos 1.5 e 1.6."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="doisfatores@exemplo.com",
            full_name="Usuario Com 2FA",
            password=SENHA,
        )
        self.device = TOTPDevice.objects.create(
            user=self.user, name="teste", confirmed=True
        )
        reset()

    def test_senha_correta_ainda_nao_cria_sessao(self):
        resposta = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": SENHA},
        )
        self.assertRedirects(resposta, reverse("accounts:otp_verify"))
        # A prova do requisito 1.6: acertar a senha não autentica ninguém.
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_codigo_valido_conclui_a_entrada(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": SENHA},
        )
        resposta = self.client.post(
            reverse("accounts:otp_verify"),
            {"token": codigo_atual(self.device)},
        )
        self.assertRedirects(resposta, reverse("accounts:profile"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_codigo_errado_nao_entra(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": SENHA},
        )
        self.client.post(reverse("accounts:otp_verify"), {"token": "000000"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_verificacao_direta_sem_senha_e_recusada(self):
        resposta = self.client.get(reverse("accounts:otp_verify"))
        self.assertRedirects(resposta, reverse("accounts:login"))


class SessaoTests(TestCase):
    """Requisitos 1.9 e 1.10."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sessao@exemplo.com",
            full_name="Usuario De Sessao",
            password=SENHA,
        )

    def test_sessao_expira_em_quinze_minutos(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 900)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)

    def test_cookie_de_sessao_e_protegido(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")

    def test_logout_apaga_a_sessao_do_banco(self):
        self.client.force_login(self.user)
        chave = self.client.session.session_key
        self.assertTrue(Session.objects.filter(session_key=chave).exists())

        self.client.post(reverse("accounts:logout"))

        # Não basta o navegador esquecer o cookie: o registro sai do banco.
        self.assertFalse(Session.objects.filter(session_key=chave).exists())


class ForcaBrutaTests(TestCase):
    """Requisito 1.11."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="alvo@exemplo.com",
            full_name="Usuario Alvo",
            password=SENHA,
        )
        reset()

    def tearDown(self):
        reset()

    def test_bloqueia_depois_do_limite_de_tentativas(self):
        url = reverse("accounts:login")
        erradas = {"username": self.user.email, "password": "chute errado"}

        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.client.post(url, erradas)

        resposta = self.client.post(url, erradas)
        # 429: a resposta que o axes devolve quando a conta está bloqueada.
        self.assertEqual(resposta.status_code, 429)

    def test_tentativas_ficam_registradas(self):
        url = reverse("accounts:login")
        erradas = {"username": self.user.email, "password": "chute errado"}

        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.client.post(url, erradas)

        tentativa = AccessAttempt.objects.first()
        self.assertIsNotNone(tentativa)
        self.assertEqual(tentativa.failures_since_start, settings.AXES_FAILURE_LIMIT)


class CadastroTests(TestCase):
    """Requisitos 1.1 e 4.4."""

    def test_senha_do_cadastro_ja_nasce_em_argon2id(self):
        self.client.post(
            reverse("accounts:register"),
            {
                "email": "novo@exemplo.com",
                "full_name": "Usuario Novo",
                "password1": SENHA,
                "password2": SENHA,
                "accept_privacy_policy": "on",
            },
        )
        novo = User.objects.get(email="novo@exemplo.com")
        self.assertTrue(novo.password.startswith("argon2$argon2id$"))

    def test_cadastro_sem_aceite_da_politica_e_recusado(self):
        self.client.post(
            reverse("accounts:register"),
            {
                "email": "semaceite@exemplo.com",
                "full_name": "Sem Aceite",
                "password1": SENHA,
                "password2": SENHA,
            },
        )
        self.assertFalse(User.objects.filter(email="semaceite@exemplo.com").exists())

    def test_senha_fraca_e_recusada(self):
        self.client.post(
            reverse("accounts:register"),
            {
                "email": "fraca@exemplo.com",
                "full_name": "Senha Fraca",
                "password1": "123456",
                "password2": "123456",
                "accept_privacy_policy": "on",
            },
        )
        self.assertFalse(User.objects.filter(email="fraca@exemplo.com").exists())