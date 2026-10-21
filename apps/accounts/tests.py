import importlib
import io
import os
import time
import urllib.error
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.management import call_command
from django.core.management.base import CommandError
from django_otp.admin import OTPAdminSite
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from axes.models import AccessAttempt, AccessAttemptExpiration
from axes.utils import reset

from apps.audit.models import AuthEvent, PasswordResetLog
from apps.privacy.models import ConsentRecord

from . import codigos_reserva
from .crypto import FalhaNaDecifragem, cifrar, decifrar, precisa_recifrar
from .emails import FalhaNoEnvio, enviar_link_de_recuperacao
from .models import EmailConfirmationToken, EncryptedTOTPDevice, PasswordResetToken

User = get_user_model()

SENHA = "TrocaEssaSenha2026"


class RelogioDosLimitesParado:
    """Fixa o relógio do django-ratelimit durante o teste.

    Os limites contam por janela de relógio ("3/m" é por minuto do relógio).
    Um teste que cruzasse a virada da janela veria a contagem zerar no meio e
    falharia de vez em quando.
    """

    def setUp(self):
        super().setUp()
        relogio = patch("django_ratelimit.core.time")
        relogio.start().time.return_value = 1_800_000_000.0
        self.addCleanup(relogio.stop)


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
        self.device = EncryptedTOTPDevice.objects.create(
            user=self.user, name="teste", confirmed=True
        )
        # Uma conta criada pelo formulário de cadastro já nasce com o aceite da
        # política. Sem ele, o perfil levaria à tela de consentimento.
        ConsentRecord.registrar_aceite(self.user)
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

    def test_tela_de_ativacao_2fa_nao_pode_ser_cacheada(self):
        self.client.force_login(self.user)

        resposta = self.client.get(reverse("accounts:otp_setup"))

        self.assertIn("no-store", resposta["Cache-Control"])


class PainelAdministrativoTests(TestCase):
    """Risco R01: o /admin/ exige o segundo fator de quem é da equipe."""

    def setUp(self):
        self.equipe = User.objects.create_superuser(
            email="equipe@exemplo.com",
            full_name="Pessoa Da Equipe",
            password=SENHA,
        )
        self.device = EncryptedTOTPDevice.objects.create(
            user=self.equipe, name="celular", confirmed=True
        )
        ConsentRecord.registrar_aceite(self.equipe)
        reset()

    def _entrar(self, com_codigo=True):
        self.client.post(
            reverse("accounts:login"),
            {"username": self.equipe.email, "password": SENHA},
        )
        if com_codigo:
            self.client.post(
                reverse("accounts:otp_verify"),
                {"token": codigo_atual(self.device)},
            )

    def test_superusuario_com_2fa_nao_entra_no_admin_so_com_senha(self):
        # Antes, o formulário do /admin/login/ criava a sessão com e-mail e
        # senha, sem pedir o código.
        resposta = self.client.post(
            reverse("admin:login"),
            {"username": self.equipe.email, "password": SENHA},
        )

        self.assertRedirects(resposta, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_sessao_sem_codigo_confirmado_nao_abre_o_admin(self):
        # Sessão de alguém da equipe que não passou pelo código nesta sessão.
        self.client.force_login(self.equipe)

        resposta = self.client.get(reverse("admin:index"))

        self.assertRedirects(
            resposta,
            f"{reverse('admin:login')}?next={reverse('admin:index')}",
            fetch_redirect_response=False,
        )

    def test_superusuario_que_confirmou_o_codigo_abre_o_admin(self):
        self._entrar()

        resposta = self.client.get(reverse("admin:index"))

        self.assertEqual(resposta.status_code, 200)

    def test_equipe_sem_2fa_ativo_nao_abre_o_admin(self):
        # Desde a C3 (R05), quem é da equipe sem 2FA nem chega a entrar.
        self.device.delete()
        self._entrar(com_codigo=False)

        resposta = self.client.get(reverse("admin:index"))

        self.assertNotEqual(resposta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cadastro_de_dispositivos_do_django_otp_saiu_do_painel(self):
        # Ele gravaria o segredo em texto puro, fora do EncryptedTOTPDevice.
        self.assertIsInstance(admin.site, OTPAdminSite)
        self.assertFalse(admin.site.is_registered(TOTPDevice))


class DoisFatoresDaEquipeTests(TestCase):
    """Risco R05: 2FA obrigatório para a equipe e convite para os demais."""

    def setUp(self):
        self.comum = User.objects.create_user(
            email="comum@exemplo.com", full_name="Pessoa Comum", password=SENHA
        )
        self.equipe = User.objects.create_user(
            email="membro@exemplo.com", full_name="Membro Da Equipe", password=SENHA,
            is_staff=True,
        )
        for user in (self.comum, self.equipe):
            ConsentRecord.registrar_aceite(user)
        reset()

    def _login(self, user):
        return self.client.post(
            reverse("accounts:login"), {"username": user.email, "password": SENHA}
        )

    def test_equipe_sem_2fa_nao_entra(self):
        # Antes, a senha bastava, e quem a tivesse podia ativar o 2FA no
        # próprio celular e abrir o painel.
        resposta = self._login(self.equipe)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "só entram com a verificação em duas etapas")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(
            AuthEvent.objects.filter(
                event=AuthEvent.Event.LOGIN_FALHOU, user=self.equipe
            ).exists()
        )

    def test_primeiro_login_sem_2fa_leva_ao_convite(self):
        resposta = self._login(self.comum)

        self.assertRedirects(resposta, reverse("accounts:otp_setup"))

    def test_logins_seguintes_sem_2fa_vao_ao_perfil(self):
        self._login(self.comum)
        self.client.post(reverse("accounts:logout"))

        resposta = self._login(self.comum)

        self.assertRedirects(resposta, reverse("accounts:profile"))

    def test_promover_equipe_exige_2fa_ativo(self):
        with self.assertRaises(CommandError):
            call_command("promover_equipe", self.comum.email, stdout=io.StringIO())
        self.comum.refresh_from_db()
        self.assertFalse(self.comum.is_staff)

        EncryptedTOTPDevice.objects.create(user=self.comum, name="celular", confirmed=True)
        call_command("promover_equipe", self.comum.email, stdout=io.StringIO())

        self.comum.refresh_from_db()
        self.assertTrue(self.comum.is_staff)
        self.assertFalse(self.comum.is_superuser)


class CodigosDeReservaTests(TestCase):
    """Risco R05: códigos de reserva para quem perdeu o celular."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="reserva@exemplo.com", full_name="Pessoa Precavida", password=SENHA
        )
        self.device = EncryptedTOTPDevice.objects.create(
            user=self.user, name="celular", confirmed=True
        )
        ConsentRecord.registrar_aceite(self.user)
        reset()

    def _senha(self):
        self.client.post(
            reverse("accounts:login"), {"username": self.user.email, "password": SENHA}
        )

    def _entrar_com_reserva(self, codigo):
        self._senha()
        return self.client.post(reverse("accounts:otp_verify"), {"codigo_reserva": codigo})

    def test_ativar_o_2fa_mostra_dez_codigos_que_nao_ficam_legiveis_no_banco(self):
        self.device.delete()
        self.client.force_login(self.user)
        self.client.get(reverse("accounts:otp_setup"))
        pendente = EncryptedTOTPDevice.objects.get(user=self.user, confirmed=False)

        resposta = self.client.post(
            reverse("accounts:otp_setup"), {"token": codigo_atual(pendente)}
        )

        codigos = resposta.context["codigos"]
        self.assertEqual(len(codigos), 10)
        self.assertIn("no-store", resposta["Cache-Control"])
        gravados = set(StaticToken.objects.values_list("token", flat=True))
        self.assertEqual(len(gravados), 10)
        for codigo in codigos:
            self.assertContains(resposta, codigo)
            self.assertNotIn(codigo, gravados)
            self.assertNotIn(codigo.replace("-", ""), gravados)

    def test_codigo_de_reserva_conclui_a_entrada_uma_vez_so(self):
        codigo = codigos_reserva.gerar_codigos(self.user)[0]

        resposta = self._entrar_com_reserva(codigo)

        self.assertRedirects(resposta, reverse("accounts:profile"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertEqual(codigos_reserva.restantes(self.user), 9)

        self.client.post(reverse("accounts:logout"))
        self._entrar_com_reserva(codigo)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_codigo_aceita_minusculas_e_sem_hifen(self):
        codigo = codigos_reserva.gerar_codigos(self.user)[0]

        self._entrar_com_reserva(codigo.replace("-", "").lower())

        self.assertIn("_auth_user_id", self.client.session)

    def test_codigo_errado_nao_entra_e_fica_na_trilha(self):
        codigos_reserva.gerar_codigos(self.user)

        resposta = self._entrar_com_reserva("AAAAA-AAAAA")

        self.assertContains(resposta, "inválido ou já usado")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(
            AuthEvent.objects.filter(
                event=AuthEvent.Event.OTP_FALHOU, detail="codigo de reserva"
            ).exists()
        )

    def test_gerar_novos_cancela_os_antigos(self):
        antigo = codigos_reserva.gerar_codigos(self.user)[0]
        self._senha()
        self.client.post(reverse("accounts:otp_verify"), {"token": codigo_atual(self.device)})

        resposta = self.client.post(reverse("accounts:codigos_reserva_novos"))

        self.assertEqual(len(resposta.context["codigos"]), 10)
        self.assertIsNone(codigos_reserva.usar_codigo(self.user, antigo))

    def test_gerar_novos_exige_sessao_com_segundo_fator(self):
        self.client.force_login(self.user)

        resposta = self.client.post(reverse("accounts:codigos_reserva_novos"))

        self.assertRedirects(resposta, reverse("accounts:profile"))
        self.assertEqual(codigos_reserva.restantes(self.user), 0)

    def test_desativar_o_2fa_apaga_os_codigos(self):
        codigos_reserva.gerar_codigos(self.user)
        self.client.force_login(self.user)

        self.client.post(
            reverse("accounts:otp_disable"),
            {"password": SENHA, "codigo": codigo_atual(self.device)},
        )

        self.assertEqual(codigos_reserva.restantes(self.user), 0)

    def test_cadastro_de_codigos_estaticos_saiu_do_painel(self):
        # Pelo painel, alguém da equipe criaria um código para outra conta.
        self.assertFalse(admin.site.is_registered(StaticDevice))


class ReautenticacaoTests(RelogioDosLimitesParado, TestCase):
    """Risco R12: desligar o 2FA e excluir a conta pedem confirmação forte."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            email="cuidadoso@exemplo.com", full_name="Pessoa Cuidadosa", password=SENHA
        )
        self.device = EncryptedTOTPDevice.objects.create(
            user=self.user, name="celular", confirmed=True
        )
        ConsentRecord.registrar_aceite(self.user)
        self.client.force_login(self.user)

    def _desativar(self, **dados):
        return self.client.post(reverse("accounts:otp_disable"), dados)

    def _tem_2fa(self):
        return EncryptedTOTPDevice.objects.filter(user=self.user).exists()

    def test_desativar_sem_senha_nem_codigo_nao_desliga(self):
        # Antes, um POST vazio na sessão aberta desligava o 2FA.
        self._desativar()

        self.assertTrue(self._tem_2fa())

    def test_desativar_com_senha_mas_codigo_errado_nao_desliga(self):
        resposta = self._desativar(password=SENHA, codigo="000000")

        self.assertContains(resposta, "Senha ou código incorretos.")
        self.assertTrue(self._tem_2fa())

    def test_desativar_com_codigo_mas_senha_errada_nao_desliga(self):
        self._desativar(password="outra senha", codigo=codigo_atual(self.device))

        self.assertTrue(self._tem_2fa())

    def test_desativar_com_senha_e_codigo_desliga(self):
        resposta = self._desativar(password=SENHA, codigo=codigo_atual(self.device))

        self.assertRedirects(resposta, reverse("accounts:profile"))
        self.assertFalse(self._tem_2fa())

    def test_codigo_de_reserva_tambem_confirma(self):
        codigo = codigos_reserva.gerar_codigos(self.user)[0]

        self._desativar(password=SENHA, codigo=codigo)

        self.assertFalse(self._tem_2fa())

    def test_equipe_nao_desativa_o_2fa(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        self._desativar(password=SENHA, codigo=codigo_atual(self.device))

        self.assertTrue(self._tem_2fa())

    def test_confirmacoes_erradas_de_desativacao_tem_limite(self):
        for _ in range(5):
            self._desativar(password=SENHA, codigo="000000")

        resposta = self._desativar(password=SENHA, codigo=codigo_atual(self.device))

        self.assertEqual(resposta.status_code, 429)
        self.assertTrue(self._tem_2fa())

    def test_exclusao_da_conta_tem_limite_de_senhas_erradas(self):
        # Antes, dava para testar senhas na tela de exclusão sem parar.
        for _ in range(5):
            self.client.post(reverse("privacy:delete_account"), {"password": "chute"})

        resposta = self.client.post(reverse("privacy:delete_account"), {"password": SENHA})

        self.assertEqual(resposta.status_code, 429)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_exclusao_com_a_senha_certa_continua_funcionando(self):
        self.client.post(reverse("privacy:delete_account"), {"password": "chute"})

        self.client.post(reverse("privacy:delete_account"), {"password": SENHA})

        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())


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


class BloqueioProgressivoTests(TestCase):
    """Risco R03: o bloqueio do axes dobra quando se repete no mesmo dia."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="repetido@exemplo.com",
            full_name="Usuario Repetido",
            password=SENHA,
        )
        reset()

    def tearDown(self):
        reset()

    def _bloquear(self):
        erradas = {"username": self.user.email, "password": "chute errado"}
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.client.post(reverse("accounts:login"), erradas)

    def _duracao_do_bloqueio(self):
        tentativa = AccessAttempt.objects.get()
        return tentativa.expiration.expires_at - tentativa.attempt_time

    def _passar_o_bloqueio(self):
        # Simula o fim do bloqueio: a tentativa vence, e o bloqueio registrado
        # na trilha fica no passado, mas dentro das últimas 24 horas.
        seis_minutos_atras = timezone.now() - timedelta(minutes=6)
        AccessAttemptExpiration.objects.update(expires_at=seis_minutos_atras)
        AccessAttempt.objects.update(attempt_time=seis_minutos_atras)
        AuthEvent.objects.filter(event=AuthEvent.Event.CONTA_BLOQUEADA).update(
            created_at=seis_minutos_atras
        )

    def test_primeiro_bloqueio_dura_cinco_minutos(self):
        self._bloquear()

        self.assertEqual(self._duracao_do_bloqueio(), timedelta(minutes=5))

    def test_segundo_bloqueio_no_mesmo_dia_dura_o_dobro(self):
        # Antes, todo bloqueio durava 5 minutos, por mais que se repetisse.
        self._bloquear()
        self._passar_o_bloqueio()

        self._bloquear()

        self.assertEqual(
            AuthEvent.objects.filter(event=AuthEvent.Event.CONTA_BLOQUEADA).count(), 2
        )
        self.assertEqual(self._duracao_do_bloqueio(), timedelta(minutes=10))

    def test_bloqueio_de_ontem_nao_conta(self):
        self._bloquear()
        self._passar_o_bloqueio()
        AuthEvent.objects.filter(event=AuthEvent.Event.CONTA_BLOQUEADA).update(
            created_at=timezone.now() - timedelta(hours=25)
        )

        self._bloquear()

        self.assertEqual(self._duracao_do_bloqueio(), timedelta(minutes=5))


@override_settings(
    LIMITES_DE_REQUISICAO={
        "login": {"por_ip": "3/m", "total": "100/m"},
        "otp": {"por_ip": "3/m", "total": "100/m"},
        "cadastro": {"por_ip": "3/m", "total": "100/m"},
        "recuperacao": {"por_ip": "3/m", "total": "100/m"},
    }
)
class LimiteDeRequisicoesTests(RelogioDosLimitesParado, TestCase):
    """Risco R03: limite por endereço e no total nas telas caras."""

    def setUp(self):
        reset()

    def tearDown(self):
        reset()

    def _tentar_login(self, numero, ip="10.0.0.1"):
        # Um e-mail diferente a cada vez: o axes, que bloqueia por conta e
        # endereço, nunca chega ao limite. É o padrão do password spraying.
        return self.client.post(
            reverse("accounts:login"),
            {"username": f"pessoa{numero}@exemplo.com", "password": "Senha2026comum"},
            REMOTE_ADDR=ip,
        )

    def test_mesmo_ip_em_muitas_contas_e_recusado(self):
        for numero in range(3):
            self.assertEqual(self._tentar_login(numero).status_code, 200)

        resposta = self._tentar_login(3)

        self.assertEqual(resposta.status_code, 429)
        self.assertTemplateUsed(resposta, "accounts/limite_excedido.html")

    def test_outro_ip_nao_e_afetado_pelo_limite_do_primeiro(self):
        for numero in range(4):
            self._tentar_login(numero, ip="10.0.0.1")

        self.assertEqual(self._tentar_login(9, ip="10.0.0.2").status_code, 200)

    @override_settings(
        LIMITES_DE_REQUISICAO={"login": {"por_ip": "100/m", "total": "3/m"}}
    )
    def test_limite_total_vale_para_muitos_ips(self):
        for numero in range(3):
            self._tentar_login(numero, ip=f"10.0.1.{numero}")

        resposta = self._tentar_login(3, ip="10.0.1.200")

        self.assertEqual(resposta.status_code, 429)

    def test_abrir_a_pagina_nao_conta(self):
        for _ in range(10):
            self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)

    def test_cadastro_recuperacao_e_codigo_tambem_tem_limite(self):
        for nome in ("accounts:register", "accounts:password_reset", "accounts:otp_verify"):
            with self.subTest(tela=nome):
                for _ in range(3):
                    self.client.post(reverse(nome), {}, REMOTE_ADDR="10.0.2.1")
                resposta = self.client.post(reverse(nome), {}, REMOTE_ADDR="10.0.2.1")
                self.assertEqual(resposta.status_code, 429)

    def test_diagnostico_do_proxy_so_registra_quando_ligado(self):
        with self.assertNoLogs("apps.accounts.limites", level="INFO"):
            self._tentar_login(0)

        with override_settings(DIAGNOSTICO_PROXY=True):
            with self.assertLogs("apps.accounts.limites", level="INFO") as registro:
                self.client.post(
                    reverse("accounts:login"),
                    {"username": "a@exemplo.com", "password": "x"},
                    REMOTE_ADDR="10.0.3.1",
                    HTTP_X_FORWARDED_FOR="200.1.2.3",
                )

        self.assertIn("x_forwarded_for=200.1.2.3", registro.output[0])


class CadastroSemEnumeracaoTests(RelogioDosLimitesParado, TestCase):
    """Risco R08: o cadastro não revela se o e-mail já tem conta."""

    def setUp(self):
        self.existente = User.objects.create_user(
            email="ja.tenho@exemplo.com", full_name="Pessoa Antiga", password=SENHA
        )
        ConsentRecord.registrar_aceite(self.existente)
        reset()

    def _cadastrar(self, email):
        return self.client.post(
            reverse("accounts:register"),
            {
                "email": email,
                "full_name": "Pessoa Nova",
                "password1": SENHA,
                "password2": SENHA,
                "accept_privacy_policy": "on",
            },
        )

    @patch("apps.accounts.views.enviar_aviso_de_conta_existente")
    @patch("apps.accounts.views.enviar_link_de_confirmacao")
    def test_resposta_e_igual_para_email_novo_e_ja_cadastrado(self, confirmacao, aviso):
        # Antes, o e-mail repetido voltava ao formulário com "Ja existe uma
        # conta com este e-mail".
        novo = self._cadastrar("novo@exemplo.com")
        repetido = self._cadastrar(self.existente.email)

        self.assertRedirects(novo, reverse("accounts:register_sent"))
        self.assertRedirects(repetido, reverse("accounts:register_sent"))
        self.assertNotContains(self.client.get(repetido.url), "Ja existe")

    @patch("apps.accounts.views.enviar_link_de_confirmacao")
    def test_conta_nova_nasce_inativa_e_so_entra_depois_do_link(self, confirmacao):
        self._cadastrar("novo@exemplo.com")
        novo = User.objects.get(email="novo@exemplo.com")
        self.assertFalse(novo.is_active)

        self.client.post(
            reverse("accounts:login"), {"username": novo.email, "password": SENHA}
        )
        self.assertNotIn("_auth_user_id", self.client.session)

        link = confirmacao.call_args.args[1]
        resposta = self.client.get(link.replace(settings.APP_BASE_URL.rstrip("/"), ""))

        self.assertRedirects(resposta, reverse("accounts:login"))
        novo.refresh_from_db()
        self.assertTrue(novo.is_active)

    @patch("apps.accounts.views.enviar_link_de_confirmacao")
    def test_link_de_confirmacao_vale_uma_vez(self, confirmacao):
        self._cadastrar("novo@exemplo.com")
        caminho = confirmacao.call_args.args[1].replace(settings.APP_BASE_URL.rstrip("/"), "")
        self.client.get(caminho)

        resposta = self.client.get(caminho)

        self.assertRedirects(resposta, reverse("accounts:register"))

    @patch("apps.accounts.views.enviar_link_de_confirmacao")
    def test_link_vencido_nao_ativa(self, confirmacao):
        self._cadastrar("novo@exemplo.com")
        EmailConfirmationToken.objects.update(expires_at=timezone.now() - timedelta(minutes=1))

        self.client.get(confirmacao.call_args.args[1].replace(settings.APP_BASE_URL.rstrip("/"), ""))

        self.assertFalse(User.objects.get(email="novo@exemplo.com").is_active)

    @patch("apps.accounts.views.enviar_aviso_de_conta_existente")
    def test_email_ja_cadastrado_nao_cria_conta_e_avisa_o_dono(self, aviso):
        self._cadastrar(self.existente.email)
        self._cadastrar(self.existente.email)

        self.assertEqual(User.objects.filter(email__iexact=self.existente.email).count(), 1)
        # Um aviso por hora: o formulário não serve para lotar a caixa de alguém.
        aviso.assert_called_once()
        self.assertEqual(aviso.call_args.args[0], self.existente)

    @patch("apps.accounts.views.enviar_link_de_confirmacao")
    def test_conta_nunca_confirmada_recebe_link_novo(self, confirmacao):
        self._cadastrar("novo@exemplo.com")
        self._cadastrar("novo@exemplo.com")

        self.assertEqual(confirmacao.call_count, 2)
        self.assertEqual(User.objects.filter(email="novo@exemplo.com").count(), 1)
        self.assertEqual(EmailConfirmationToken.objects.count(), 1)

    @patch("apps.accounts.views.enviar_link_de_confirmacao", side_effect=FalhaNoEnvio("fora do ar"))
    def test_falha_no_envio_nao_muda_a_resposta(self, confirmacao):
        resposta = self._cadastrar("novo@exemplo.com")

        self.assertRedirects(resposta, reverse("accounts:register_sent"))


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

class RecuperacaoDeSenhaTests(TestCase):
    """Requisitos 2.1 a 2.7."""

    SENHA_NOVA = "OutraSenhaBoa2026"

    def setUp(self):
        self.user = User.objects.create_user(
            email="esqueci@exemplo.com",
            full_name="Usuario Esquecido",
            password=SENHA,
        )
        reset()

    def tearDown(self):
        reset()

    def pedir_link(self, email=None):
        """Faz a solicitação e devolve o link que teria ido no e-mail.

        O envio é substituído por um espião: o token em texto puro só existe
        dentro do link, então é ali que o teste precisa olhar. Substituir o
        envio também impede que a suíte consuma a cota do Brevo.
        """
        with patch("apps.accounts.views.enviar_link_de_recuperacao") as envio:
            resposta = self.client.post(
                reverse("accounts:password_reset"),
                {"email": email or self.user.email},
            )
        link = envio.call_args[0][1] if envio.call_args else None
        return resposta, link

    # --- 2.1 fluxo completo -------------------------------------------------

    def trocar_senha(self, link, dados):
        """Abre o link do e-mail e envia a senha nova na tela sem o token.

        Se o link for recusado, devolve a resposta de recusa, como faria o
        navegador de quem clicou.
        """
        resposta = self.client.get(link)
        if resposta.status_code != 302:
            return resposta
        return self.client.post(reverse("accounts:password_reset_new"), dados)

    def test_link_tira_o_token_da_url_antes_do_formulario(self):
        # Risco R13. Antes, o formulário ficava no endereço com o token, que
        # ia para o histórico e para o Referer.
        _, link = self.pedir_link()
        token = link.rstrip("/").rsplit("/", 1)[-1]

        resposta = self.client.get(link)

        self.assertRedirects(resposta, reverse("accounts:password_reset_new"))
        self.assertNotIn(token, resposta["Location"])
        # A sessão guarda o identificador do registro, não o token.
        self.assertNotIn(token, str(dict(self.client.session)))
        formulario = self.client.get(reverse("accounts:password_reset_new"))
        self.assertContains(formulario, "new_password1")
        self.assertIn("no-store", formulario["Cache-Control"])

    def test_tela_da_senha_nova_sem_passar_pelo_link_e_recusada(self):
        resposta = self.client.get(reverse("accounts:password_reset_new"))

        self.assertEqual(resposta.status_code, 400)
        self.assertNotContains(resposta, "new_password1", status_code=400)

    def test_token_que_vence_com_a_tela_aberta_nao_troca_a_senha(self):
        _, link = self.pedir_link()
        self.client.get(link)
        PasswordResetToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        resposta = self.client.post(
            reverse("accounts:password_reset_new"),
            {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA},
        )

        self.assertEqual(resposta.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA))

    def test_depois_da_troca_a_tela_nao_abre_de_novo(self):
        _, link = self.pedir_link()
        self.trocar_senha(link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA})

        resposta = self.client.get(reverse("accounts:password_reset_new"))

        self.assertEqual(resposta.status_code, 400)

    def test_fluxo_completo_troca_a_senha(self):
        _, link = self.pedir_link()
        self.trocar_senha(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.SENHA_NOVA))
        self.assertFalse(self.user.check_password(SENHA))

    def test_senha_redefinida_continua_em_argon2id(self):
        _, link = self.pedir_link()
        self.trocar_senha(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        self.user.refresh_from_db()
        # A senha nova passa pelo mesmo hasher do cadastro, e não por um
        # caminho paralelo mais fraco.
        self.assertTrue(self.user.password.startswith("argon2$argon2id$"))

    def test_senha_nova_fraca_e_recusada(self):
        _, link = self.pedir_link()
        self.trocar_senha(link, {"new_password1": "123456", "new_password2": "123456"})

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA))

    def test_resposta_e_igual_para_email_inexistente(self):
        # Anti-enumeração: nada na resposta diferencia uma conta que existe de
        # uma que não existe.
        com_conta, _ = self.pedir_link()
        sem_conta, _ = self.pedir_link("ninguem@exemplo.com")

        self.assertEqual(com_conta.status_code, sem_conta.status_code)
        self.assertEqual(com_conta["Location"], sem_conta["Location"])

    # --- 2.2 token criptograficamente seguro --------------------------------

    def test_token_nao_e_gravado_em_texto_puro(self):
        _, token_puro = PasswordResetToken.emitir(self.user)
        registro = PasswordResetToken.objects.get()

        self.assertNotEqual(registro.token_hash, token_puro)
        self.assertEqual(
            registro.token_hash, PasswordResetToken.calcular_hash(token_puro)
        )
        # 64 caracteres: o tamanho de um SHA-256 em hexadecimal.
        self.assertEqual(len(registro.token_hash), 64)

    def test_tokens_emitidos_sao_diferentes(self):
        outro = User.objects.create_user(
            email="outro2@exemplo.com", full_name="Outro", password=SENHA
        )
        _, primeiro = PasswordResetToken.emitir(self.user)
        _, segundo = PasswordResetToken.emitir(outro)

        self.assertNotEqual(primeiro, segundo)
        # 32 bytes em base64 seguro para URL resultam em 43 caracteres.
        self.assertEqual(len(primeiro), 43)

    # --- 2.3 expiração ------------------------------------------------------

    def test_token_nasce_com_prazo_configurado(self):
        registro, _ = PasswordResetToken.emitir(self.user)
        prazo = registro.expires_at - registro.created_at

        self.assertAlmostEqual(
            prazo.total_seconds(),
            settings.PASSWORD_RESET_TOKEN_TIMEOUT.total_seconds(),
            delta=5,
        )

    # --- 2.4 invalidação após o uso -----------------------------------------

    def test_token_e_marcado_como_usado(self):
        _, link = self.pedir_link()
        self.trocar_senha(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        registro = PasswordResetToken.objects.get()
        self.assertIsNotNone(registro.used_at)

    def test_mesmo_link_nao_serve_duas_vezes(self):
        _, link = self.pedir_link()
        self.trocar_senha(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        terceira = "TerceiraSenhaBoa2026"
        resposta = self.trocar_senha(
            link, {"new_password1": terceira, "new_password2": terceira}
        )

        self.assertEqual(resposta.status_code, 400)
        self.user.refresh_from_db()
        # Continua valendo a senha da primeira troca.
        self.assertTrue(self.user.check_password(self.SENHA_NOVA))

    def test_pedido_novo_cancela_o_link_anterior(self):
        _, primeiro_link = self.pedir_link()
        self.pedir_link()

        resposta = self.trocar_senha(
            primeiro_link,
            {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA},
        )

        self.assertEqual(resposta.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA))

    # --- 2.5 falha correta para token expirado ------------------------------

    def test_token_expirado_nao_troca_a_senha(self):
        _, link = self.pedir_link()
        # Empurra o vencimento para trás em vez de esperar meia hora.
        PasswordResetToken.objects.update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        resposta = self.trocar_senha(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertTemplateUsed(resposta, "accounts/password_reset_invalid.html")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA))

    def test_token_expirado_nem_mostra_o_formulario(self):
        _, link = self.pedir_link()
        PasswordResetToken.objects.update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        resposta = self.client.get(link)

        self.assertEqual(resposta.status_code, 400)
        self.assertNotContains(resposta, "new_password1", status_code=400)

    def test_token_inventado_e_recusado(self):
        resposta = self.client.get(
            reverse("accounts:password_reset_confirm", args=["token-que-nunca-existiu"])
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertTemplateUsed(resposta, "accounts/password_reset_invalid.html")

    # --- 2.6 e 2.7 registro em log ------------------------------------------

    def test_solicitacao_fica_registrada(self):
        self.pedir_link()

        registro = PasswordResetLog.objects.filter(
            event=PasswordResetLog.Event.SOLICITADO
        ).first()
        self.assertIsNotNone(registro)
        # A conta é identificada pelo identificador interno, não pelo endereço.
        self.assertEqual(registro.user, self.user)

    def test_solicitacao_para_email_inexistente_tambem_fica_registrada(self):
        self.pedir_link("ninguem@exemplo.com")

        registro = PasswordResetLog.objects.filter(
            event=PasswordResetLog.Event.SOLICITADO
        ).first()
        # O pedido entra na trilha mesmo sem conta correspondente, com usuário
        # nulo. O endereço digitado não é gravado em lugar nenhum.
        self.assertIsNotNone(registro)
        self.assertIsNone(registro.user)

    def test_sucesso_do_processo_fica_registrado(self):
        _, link = self.pedir_link()
        self.trocar_senha(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        self.assertTrue(
            PasswordResetLog.objects.filter(
                event=PasswordResetLog.Event.SENHA_REDEFINIDA, user=self.user
            ).exists()
        )

    def test_falha_do_processo_fica_registrada(self):
        _, link = self.pedir_link()
        PasswordResetToken.objects.update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.client.get(link)

        self.assertTrue(
            PasswordResetLog.objects.filter(
                event=PasswordResetLog.Event.TOKEN_EXPIRADO
            ).exists()
        )

    def test_falha_no_envio_do_email_fica_registrada(self):
        with patch(
            "apps.accounts.views.enviar_link_de_recuperacao",
            side_effect=FalhaNoEnvio("Brevo fora do ar"),
        ):
            resposta = self.client.post(
                reverse("accounts:password_reset"), {"email": self.user.email}
            )

        # A pessoa vê a mesma tela de sempre, mas a falha fica no log.
        self.assertRedirects(resposta, reverse("accounts:password_reset_sent"))
        self.assertTrue(
            PasswordResetLog.objects.filter(
                event=PasswordResetLog.Event.EMAIL_FALHOU
            ).exists()
        )

    def test_excesso_de_pedidos_nao_gera_mais_links(self):
        for _ in range(settings.PASSWORD_RESET_MAX_REQUESTS + 2):
            self.pedir_link()

        self.assertEqual(
            PasswordResetToken.objects.count(), settings.PASSWORD_RESET_MAX_REQUESTS
        )
        self.assertTrue(
            PasswordResetLog.objects.filter(
                event=PasswordResetLog.Event.LIMITE_EXCEDIDO
            ).exists()
        )

    # --- privacidade da trilha de auditoria ---------------------------------

    def test_log_nao_guarda_email_token_nem_senha(self):
        """Percorre o fluxo inteiro e varre todos os campos de todos os registros.

        Cobre também os caminhos de falha, que são onde texto vindo de fora
        costuma entrar no log sem ninguém perceber.
        """
        _, link = self.pedir_link()
        token = link.rstrip("/").rsplit("/", 1)[-1]

        # Link inventado, troca concluída e reuso do mesmo link.
        self.client.get(
            reverse("accounts:password_reset_confirm", args=["token-inventado"])
        )
        self.trocar_senha(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )
        self.trocar_senha(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        registros = PasswordResetLog.objects.all()
        # Se a varredura não viu evento nenhum, o teste não provaria nada.
        self.assertGreaterEqual(registros.count(), 4)

        proibidos = [self.user.email, token, SENHA, self.SENHA_NOVA]
        for registro in registros:
            gravado = " ".join(str(valor) for valor in registro.__dict__.values())
            for proibido in proibidos:
                self.assertNotIn(proibido, gravado)

    def test_falha_do_brevo_nao_vaza_o_destinatario_no_log(self):
        # O Brevo repete o endereço recusado no corpo da resposta. Só o código
        # HTTP pode chegar ao log.
        erro = urllib.error.HTTPError("url", 400, "Bad Request", {}, None)
        erro.read = lambda: f'{{"message":"Invalid recipient {self.user.email}"}}'.encode()

        with self.settings(
            BREVO_API_KEY="chave-de-teste", BREVO_SENDER_EMAIL="remetente@exemplo.com"
        ):
            with patch("urllib.request.urlopen", side_effect=erro):
                self.client.post(
                    reverse("accounts:password_reset"), {"email": self.user.email}
                )

        registro = PasswordResetLog.objects.get(
            event=PasswordResetLog.Event.EMAIL_FALHOU
        )
        self.assertNotIn(self.user.email, registro.detail)
        self.assertIn("400", registro.detail)

    def test_sem_chave_configurada_em_producao_o_envio_falha(self):
        # Com DEBUG desligado, chave ausente é erro. Imprimir o link seria
        # gravar um token válido na saída do servidor.
        with self.settings(BREVO_API_KEY="", DEBUG=False):
            with self.assertRaises(FalhaNoEnvio):
                enviar_link_de_recuperacao(self.user, "https://exemplo/conta/x/")

    # --- texto da interface -------------------------------------------------

    def test_tela_de_envio_informa_o_prazo_exato(self):
        resposta = self.client.get(reverse("accounts:password_reset_sent"))

        minutos = int(settings.PASSWORD_RESET_TOKEN_TIMEOUT.total_seconds() // 60)
        self.assertContains(resposta, f"{minutos} minutos")

    def test_tela_de_envio_nao_explica_a_estrategia_anti_enumeracao(self):
        resposta = self.client.get(reverse("accounts:password_reset_sent"))

        # Explicar a defesa na tela confunde quem só quer a senha de volta e
        # sinaliza a existência do controle para quem procura brecha.
        self.assertNotContains(resposta, "proposital")
        self.assertNotContains(resposta, "descobrir quem tem conta")


class TrocaDeChavesTests(TestCase):
    """Risco R02: trocar as chaves sem perder segredos, sessões nem códigos."""

    CHAVE_ANTIGA = b"a" * 32
    CHAVE_NOVA = b"n" * 32

    def setUp(self):
        self.user = User.objects.create_user(
            email="troca@exemplo.com", full_name="Pessoa Da Troca", password=SENHA
        )
        ConsentRecord.registrar_aceite(self.user)
        reset()

    def test_valor_cifrado_com_a_chave_antiga_continua_legivel(self):
        with override_settings(FIELD_ENCRYPTION_KEY=self.CHAVE_ANTIGA):
            valor = cifrar(b"segredo", "contexto")

        with override_settings(
            FIELD_ENCRYPTION_KEY=self.CHAVE_NOVA, FIELD_ENCRYPTION_OLD_KEYS=[self.CHAVE_ANTIGA]
        ):
            self.assertEqual(decifrar(valor, "contexto"), b"segredo")
            self.assertTrue(precisa_recifrar(valor))
            self.assertFalse(precisa_recifrar(cifrar(b"segredo", "contexto")))

    def test_sem_a_chave_antiga_o_valor_nao_e_lido(self):
        with override_settings(FIELD_ENCRYPTION_KEY=self.CHAVE_ANTIGA):
            valor = cifrar(b"segredo", "contexto")

        with override_settings(FIELD_ENCRYPTION_KEY=self.CHAVE_NOVA, FIELD_ENCRYPTION_OLD_KEYS=[]):
            with self.assertRaises(FalhaNaDecifragem):
                decifrar(valor, "contexto")

    def test_valor_gravado_antes_do_id_da_chave_continua_legivel(self):
        # Os segredos já gravados em produção não têm o id da chave.
        with override_settings(FIELD_ENCRYPTION_KEY=self.CHAVE_ANTIGA):
            valor = cifrar(b"segredo", "contexto")
        prefixo, _id, corpo = valor.split("$")
        antigo = f"{prefixo}${corpo}"

        with override_settings(
            FIELD_ENCRYPTION_KEY=self.CHAVE_NOVA, FIELD_ENCRYPTION_OLD_KEYS=[self.CHAVE_ANTIGA]
        ):
            self.assertEqual(decifrar(antigo, "contexto"), b"segredo")
            self.assertTrue(precisa_recifrar(antigo))

    def test_login_passa_o_segredo_do_2fa_para_a_chave_nova(self):
        with override_settings(FIELD_ENCRYPTION_KEY=self.CHAVE_ANTIGA):
            device = EncryptedTOTPDevice.objects.create(
                user=self.user, name="celular", confirmed=True
            )
            codigo = codigo_atual(device)

        with override_settings(
            FIELD_ENCRYPTION_KEY=self.CHAVE_NOVA, FIELD_ENCRYPTION_OLD_KEYS=[self.CHAVE_ANTIGA]
        ):
            self.client.post(
                reverse("accounts:login"), {"username": self.user.email, "password": SENHA}
            )
            self.client.post(reverse("accounts:otp_verify"), {"token": codigo})

            self.assertIn("_auth_user_id", self.client.session)
            device.refresh_from_db()
            self.assertFalse(precisa_recifrar(device.key))

        # Depois disso, a chave antiga já não é necessária.
        with override_settings(FIELD_ENCRYPTION_KEY=self.CHAVE_NOVA, FIELD_ENCRYPTION_OLD_KEYS=[]):
            device.refresh_from_db()
            self.assertEqual(len(device.bin_key), 20)

    def test_codigo_de_reserva_vale_depois_da_troca_da_secret_key(self):
        with override_settings(SECRET_KEY="chave-antiga-" + "x" * 40):
            codigo = codigos_reserva.gerar_codigos(self.user)[0]

        with override_settings(
            SECRET_KEY="chave-nova-" + "y" * 40,
            SECRET_KEY_FALLBACKS=["chave-antiga-" + "x" * 40],
        ):
            self.assertIsNotNone(codigos_reserva.usar_codigo(self.user, codigo))


class CriptografiaEmRepousoTests(TestCase):
    """Requisitos 3.4, 3.5 e 3.6."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cifrado@exemplo.com",
            full_name="Usuario Cifrado",
            password=SENHA,
        )
        self.device = EncryptedTOTPDevice.objects.create(
            user=self.user, name="teste", confirmed=True
        )

    def valor_gravado_no_banco(self, device):
        # Lido pelo modelo original do django-otp, sem a camada que decifra: é
        # exatamente o que apareceria em um vazamento da tabela.
        return TOTPDevice.objects.get(pk=device.pk).key

    def test_segredo_do_2fa_nao_fica_em_texto_puro(self):
        gravado = self.valor_gravado_no_banco(self.device)
        segredo_em_hex = self.device.bin_key.hex()

        self.assertTrue(gravado.startswith("aes256gcm$"))
        self.assertNotIn(segredo_em_hex, gravado)

    def test_codigo_do_autenticador_continua_valido(self):
        # Cifrar não pode quebrar o 2FA: o código gerado a partir do segredo
        # decifrado precisa ser aceito normalmente.
        self.assertTrue(self.device.verify_token(codigo_atual(self.device)))

    def test_texto_cifrado_cabe_no_campo_do_django_otp(self):
        # O campo "key" do django-otp tem 80 caracteres. Se o texto cifrado não
        # coubesse, o MySQL recusaria a gravação em modo estrito.
        self.assertLessEqual(len(self.valor_gravado_no_banco(self.device)), 80)

    def test_mesmo_segredo_gera_textos_cifrados_diferentes(self):
        # Nonce aleatório a cada cifragem: dois valores iguais não produzem o
        # mesmo texto, então o banco não revela quais contas compartilham dados.
        self.assertNotEqual(cifrar(b"segredo", "c"), cifrar(b"segredo", "c"))

    def test_valor_alterado_no_banco_e_recusado(self):
        gravado = self.valor_gravado_no_banco(self.device)
        # Troca um único caractere do meio do texto cifrado.
        meio = len(gravado) // 2
        alterado = gravado[:meio] + ("A" if gravado[meio] != "A" else "B") + gravado[meio + 1:]
        TOTPDevice.objects.filter(pk=self.device.pk).update(key=alterado)

        device = EncryptedTOTPDevice.objects.get(pk=self.device.pk)
        with self.assertRaises(FalhaNaDecifragem):
            device.bin_key

    def test_segredo_copiado_para_outra_conta_nao_decifra(self):
        # O contexto amarra o texto cifrado à conta dona. Copiar o valor para
        # a linha de outra pessoa não transfere o 2FA.
        outro = User.objects.create_user(
            email="copia@exemplo.com", full_name="Outra Conta", password=SENHA
        )
        copia = EncryptedTOTPDevice.objects.create(user=outro, name="copia")
        TOTPDevice.objects.filter(pk=copia.pk).update(
            key=self.valor_gravado_no_banco(self.device)
        )

        copia.refresh_from_db()
        with self.assertRaises(FalhaNaDecifragem):
            copia.bin_key

    def test_chave_errada_nao_decifra(self):
        valor = cifrar(b"segredo", "contexto")
        with override_settings(FIELD_ENCRYPTION_KEY=os.urandom(32)):
            with self.assertRaises(FalhaNaDecifragem):
                decifrar(valor, "contexto")

    def test_texto_puro_nao_e_aceito_como_cifrado(self):
        with self.assertRaises(FalhaNaDecifragem):
            decifrar("3132333435363738393031323334353637383930", "contexto")

    def test_migracao_cifra_segredos_gravados_antes(self):
        # Simula uma conta que ativou o 2FA antes do requisito 3.4, com o
        # segredo gravado em texto puro pelo modelo original do django-otp.
        antigo = TOTPDevice.objects.create(user=self.user, name="antigo")
        segredo_original = antigo.key
        self.assertFalse(antigo.key.startswith("aes256gcm$"))

        migracao = importlib.import_module(
            "apps.accounts.migrations.0004_cifra_segredos_2fa_existentes"
        )

        class EditorFalso:
            connection = type("Conexao", (), {"alias": "default"})()

        from django.apps import apps as registro
        migracao.cifrar_segredos(registro, EditorFalso())

        convertido = EncryptedTOTPDevice.objects.get(pk=antigo.pk)
        self.assertTrue(convertido.key.startswith("aes256gcm$"))
        # O segredo continua o mesmo, só mudou a forma de guardar: o celular
        # que já estava configurado segue gerando códigos válidos.
        self.assertEqual(convertido.bin_key.hex(), segredo_original)


class ComunicacaoSeguraTests(TestCase):
    """Requisitos 3.1 e 3.2.

    Os ajustes de HTTPS só ligam com DEBUG desligado. Aqui eles são ativados à
    força para provar o comportamento que o Render tem em produção.
    """

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_http_e_redirecionado_para_https_com_301(self):
        resposta = self.client.get("/", secure=False)

        self.assertEqual(resposta.status_code, 301)
        self.assertTrue(resposta["Location"].startswith("https://"))

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_https_e_atendido_sem_redirecionamento(self):
        resposta = self.client.get("/", secure=True)
        self.assertEqual(resposta.status_code, 200)

    @override_settings(
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
    )
    def test_resposta_https_envia_hsts(self):
        resposta = self.client.get("/", secure=True)
        self.assertEqual(
            resposta["Strict-Transport-Security"],
            "max-age=31536000; includeSubDomains; preload",
        )

    @override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
                       SECURE_SSL_REDIRECT=True)
    def test_requisicao_vinda_do_proxy_do_render_nao_entra_em_loop(self):
        # O Render entrega a requisição ao Django em HTTP, com o cabeçalho
        # avisando que o navegador usou HTTPS. Sem SECURE_PROXY_SSL_HEADER, o
        # Django redirecionaria para https de novo, para sempre.
        resposta = self.client.get("/", secure=False, HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(resposta.status_code, 200)
