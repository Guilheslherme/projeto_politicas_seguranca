import json
import re
from pathlib import Path

from axes.models import AccessAttempt, AccessLog
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import EncryptedTOTPDevice, PasswordResetToken
from apps.audit.models import AuthEvent, PasswordResetLog

from .models import ConsentRecord

User = get_user_model()

SENHA = "TrocaEssaSenha2026"
IP_DE_TESTE = "203.0.113.7"  # faixa reservada para documentação (RFC 5737)


class MinimizacaoTests(TestCase):
    """Requisito 4.3."""

    def test_modelo_de_usuario_so_tem_os_campos_necessarios(self):
        # Trava contra coleta silenciosa: quem acrescentar um campo à conta, um
        # CPF ou um dado de saúde, por exemplo, faz este teste falhar e precisa
        # atualizar a Política de Privacidade e o dicionário de dados junto.
        campos = {campo.name for campo in User._meta.concrete_fields}
        self.assertEqual(
            campos,
            {
                "id", "password", "last_login", "is_superuser", "email",
                "full_name", "is_active", "is_staff", "two_factor_enabled",
                "date_joined", "last_password_change",
            },
        )

    def test_cadastro_pede_apenas_nome_email_e_senha(self):
        resposta = self.client.get(reverse("accounts:register"))
        campos = set(resposta.context["form"].fields)
        self.assertEqual(
            campos,
            {"email", "full_name", "password1", "password2", "accept_privacy_policy"},
        )

    def test_politica_de_privacidade_e_publica(self):
        resposta = self.client.get(reverse("privacy:policy"))
        self.assertEqual(resposta.status_code, 200)
        # A política precisa continuar declarando que guardar material depende
        # de consentimento específico, e não do aceite geral (Art. 8º, §4º). Se
        # essa frase sumir do texto, o teste falha e alguém tem que decidir
        # conscientemente tirá-la, em vez de perdê-la numa revisão distraída.
        self.assertContains(resposta, "consentimento específico")
        self.assertContains(resposta, "6 meses")
        self.assertNotContains(resposta, "Google Fonts")
        self.assertContains(resposta, "Oregon")
        self.assertContains(resposta, "São Francisco")
        self.assertContains(resposta, "Art. 33")


class ConsentimentoTests(TestCase):
    """Requisitos 4.4, 4.5, 4.6 e 4.7."""

    def cadastrar(self, aceite=True):
        dados = {
            "email": "titular@exemplo.com",
            "full_name": "Pessoa Titular",
            "password1": SENHA,
            "password2": SENHA,
        }
        if aceite:
            dados["accept_privacy_policy"] = "on"
        return self.client.post(reverse("accounts:register"), dados)

    def test_cadastro_grava_o_aceite_com_finalidade_versao_e_data(self):
        self.cadastrar()

        registro = ConsentRecord.objects.get()
        self.assertEqual(registro.user.email, "titular@exemplo.com")
        self.assertEqual(registro.purpose, ConsentRecord.Purpose.CONTA)
        self.assertEqual(registro.policy_version, "1.1")
        self.assertIsNotNone(registro.granted_at)
        self.assertTrue(registro.is_active)

    def test_cadastro_sem_aceite_nao_cria_conta_nem_registro(self):
        self.cadastrar(aceite=False)

        self.assertFalse(User.objects.exists())
        self.assertFalse(ConsentRecord.objects.exists())

    def test_conta_sem_aceite_e_levada_a_tela_de_consentimento(self):
        # Conta criada por fora do cadastro, como as que existiam antes de o
        # aceite ser gravado.
        user = User.objects.create_user(
            email="antiga@exemplo.com", full_name="Conta Antiga", password=SENHA
        )
        self.client.force_login(user)

        resposta = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(resposta, reverse("privacy:consent"))

    def test_aceite_pela_tela_libera_a_conta(self):
        user = User.objects.create_user(
            email="antiga@exemplo.com", full_name="Conta Antiga", password=SENHA
        )
        self.client.force_login(user)

        self.client.post(reverse("privacy:consent"), {"accept": "on"})

        self.assertTrue(ConsentRecord.tem_consentimento_vigente(user))
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_tela_de_consentimento_recusa_caixa_desmarcada(self):
        user = User.objects.create_user(
            email="antiga@exemplo.com", full_name="Conta Antiga", password=SENHA
        )
        self.client.force_login(user)

        self.client.post(reverse("privacy:consent"), {})
        self.assertFalse(ConsentRecord.objects.exists())

    def test_nova_versao_da_politica_exige_novo_aceite(self):
        user = User.objects.create_user(
            email="versao@exemplo.com", full_name="Pessoa Versao", password=SENHA
        )
        ConsentRecord.registrar_aceite(user)
        self.client.force_login(user)

        with override_settings(PRIVACY_POLICY_VERSION="2.0"):
            resposta = self.client.get(reverse("accounts:profile"))
            self.assertRedirects(resposta, reverse("privacy:consent"))

            self.client.post(reverse("privacy:consent"), {"accept": "on"})

        # O aceite antigo continua no histórico, ao lado do novo.
        versoes = set(ConsentRecord.objects.filter(user=user).values_list("policy_version", flat=True))
        self.assertEqual(versoes, {"1.1", "2.0"})

    def test_revogacao_registra_a_data_e_preserva_o_historico(self):
        self.cadastrar()
        user = User.objects.get()
        # Desde o R08, a conta só entra depois de confirmar o e-mail.
        user.is_active = True
        user.save(update_fields=["is_active"])
        self.client.force_login(user)

        self.client.post(reverse("privacy:delete_account"), {"password": SENHA})

        registro = ConsentRecord.objects.get()
        self.assertIsNotNone(registro.revoked_at)
        # Sem vínculo com a conta, que não existe mais, mas com finalidade,
        # versão e datas preservadas.
        self.assertIsNone(registro.user)
        self.assertEqual(registro.policy_version, "1.1")


class DireitosDoTitularTests(TestCase):
    """Requisitos 4.8, 4.9 e 4.10."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="titular@exemplo.com", full_name="Pessoa Titular", password=SENHA
        )
        ConsentRecord.registrar_aceite(self.user)
        self.device = EncryptedTOTPDevice.objects.create(
            user=self.user, name="teste", confirmed=True
        )
        PasswordResetToken.emitir(self.user)
        PasswordResetLog.objects.create(
            event=PasswordResetLog.Event.SOLICITADO,
            user=self.user,
            ip_address=IP_DE_TESTE,
            user_agent="Navegador de Teste",
        )
        request = RequestFactory().get(
            "/",
            REMOTE_ADDR=IP_DE_TESTE,
            HTTP_USER_AGENT="Navegador da Trilha",
        )
        self.evento_autenticacao = AuthEvent.registrar(
            request,
            AuthEvent.Event.LOGIN_OK,
            user=self.user,
            detail="login de teste",
        )
        AccessLog.objects.create(
            username=self.user.email, ip_address=IP_DE_TESTE,
            user_agent="Navegador de Teste", http_accept="*/*", path_info="/conta/entrar/",
        )
        # Com letras maiúsculas, como alguém poderia ter digitado no login.
        AccessAttempt.objects.create(
            username="Titular@Exemplo.com", ip_address=IP_DE_TESTE,
            user_agent="Navegador de Teste", http_accept="*/*", path_info="/conta/entrar/",
            get_data="", post_data="", failures_since_start=2,
        )
        self.client.force_login(self.user)

    def credenciais_proibidas(self):
        return [self.user.password, self.device.key, self.device.bin_key.hex()]

    # --- 4.8 consulta -------------------------------------------------------

    def test_consulta_mostra_dados_da_conta_e_registros(self):
        resposta = self.client.get(reverse("privacy:my_data"))

        self.assertIn("no-store", resposta["Cache-Control"])
        self.assertContains(resposta, "titular@exemplo.com")
        self.assertContains(resposta, "Pessoa Titular")
        self.assertContains(resposta, IP_DE_TESTE)
        self.assertContains(resposta, "Navegador da Trilha")
        self.assertContains(resposta, str(self.user.pk))
        self.assertContains(resposta, "Criação e manutenção da conta")
        self.assertContains(resposta, "Login concluído")

    def test_consulta_nao_exibe_credenciais(self):
        conteudo = self.client.get(reverse("privacy:my_data")).content.decode()
        for proibido in self.credenciais_proibidas():
            self.assertNotIn(proibido, conteudo)

    # --- 4.9 exportação -----------------------------------------------------

    def test_exportacao_gera_arquivo_json_para_download(self):
        resposta = self.client.post(reverse("privacy:export_data"))

        self.assertEqual(resposta["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("attachment;", resposta["Content-Disposition"])
        self.assertEqual(resposta["Cache-Control"], "no-store")

        dados = json.loads(resposta.content)
        self.assertEqual(dados["conta"]["email"], "titular@exemplo.com")
        self.assertEqual(len(dados["consentimentos"]), 1)
        eventos = dados["registros_de_seguranca"]["trilha_de_autenticacao"]
        evento_teste = next(evento for evento in eventos if evento["endereco_ip"] == IP_DE_TESTE)
        self.assertEqual(evento_teste["identificador_selado"], self.user.pk)
        self.assertEqual(evento_teste["navegador"], "Navegador da Trilha")
        # O login do próprio teste também é registrado pelo django-axes, então
        # a conferência procura o acesso criado no setUp, e não uma contagem.
        ips = {a["endereco_ip"] for a in dados["registros_de_seguranca"]["acessos_realizados"]}
        self.assertIn(IP_DE_TESTE, ips)
        # Encontrada mesmo gravada com maiúsculas no django-axes.
        self.assertEqual(
            len(dados["registros_de_seguranca"]["tentativas_de_acesso_malsucedidas"]), 1
        )

    def test_exportacao_nao_inclui_credenciais(self):
        conteudo = self.client.post(reverse("privacy:export_data")).content.decode()
        for proibido in self.credenciais_proibidas():
            self.assertNotIn(proibido, conteudo)

    def test_exportacao_nao_aceita_get(self):
        resposta = self.client.get(reverse("privacy:export_data"))
        self.assertEqual(resposta.status_code, 405)

    # --- 4.10 exclusão ------------------------------------------------------

    def test_exclusao_exige_a_senha_correta(self):
        self.client.post(reverse("privacy:delete_account"), {"password": "senha errada"})
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_exclusao_apaga_a_conta_e_os_dados_pessoais(self):
        user_id = self.user.pk
        resposta = self.client.post(reverse("privacy:delete_account"), {"password": SENHA})

        self.assertRedirects(resposta, reverse("home"))
        self.assertFalse(User.objects.filter(pk=user_id).exists())
        self.assertFalse(EncryptedTOTPDevice.objects.filter(user_id=user_id).exists())
        self.assertFalse(PasswordResetToken.objects.filter(user_id=user_id).exists())
        self.assertFalse(AccessLog.objects.filter(username__iexact="titular@exemplo.com").exists())
        self.assertFalse(AccessAttempt.objects.filter(username__iexact="titular@exemplo.com").exists())
        # A sessão também foi encerrada.
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_exclusao_anonimiza_a_trilha_de_recuperacao(self):
        self.client.post(reverse("privacy:delete_account"), {"password": SENHA})

        evento = PasswordResetLog.objects.get()
        # O fato fica registrado, mas nada nele aponta para a pessoa.
        self.assertEqual(evento.event, PasswordResetLog.Event.SOLICITADO)
        self.assertIsNone(evento.user)
        self.assertIsNone(evento.ip_address)
        self.assertEqual(evento.user_agent, "")

    def test_tela_de_exclusao_continua_acessivel_sem_consentimento(self):
        # Recusar a política não pode deixar a pessoa sem como sair do sistema.
        ConsentRecord.objects.update(policy_version="0.9")
        resposta = self.client.get(reverse("privacy:delete_account"))
        self.assertEqual(resposta.status_code, 200)


class CabecalhosEFontesLocaisTests(TestCase):
    """Content Security Policy por nonce e fonte servida pelos estáticos."""

    def test_csp_aplica_nonce_unico_a_scripts_inline(self):
        resposta = self.client.get(reverse("home"))
        csp = resposta["Content-Security-Policy"]
        correspondencia = re.search(r"script-src 'self' 'nonce-([^']+)'", csp)

        self.assertIsNotNone(correspondencia)
        nonce = correspondencia.group(1)
        self.assertContains(resposta, f'<script nonce="{nonce}">')
        self.assertIn("font-src 'self'", csp)
        self.assertNotIn("'unsafe-inline'", csp)

        outra_resposta = self.client.get(reverse("home"))
        outro_csp = outra_resposta["Content-Security-Policy"]
        outro_nonce = re.search(r"script-src 'self' 'nonce-([^']+)'", outro_csp).group(1)
        self.assertNotEqual(nonce, outro_nonce)

    def test_nonce_tambem_cobre_script_da_tela_de_consentimento(self):
        user = User.objects.create_user(
            email="csp@exemplo.com", full_name="Pessoa CSP", password=SENHA
        )
        ConsentRecord.registrar_aceite(user)
        self.client.force_login(user)

        resposta = self.client.get(reverse("catalog:consentimento_materiais"))
        nonce = re.search(
            r"script-src 'self' 'nonce-([^']+)'", resposta["Content-Security-Policy"]
        ).group(1)

        self.assertContains(resposta, f'<script nonce="{nonce}">')

    def test_outfit_e_carregada_localmente_e_a_politica_nao_cita_google_fonts(self):
        base = Path(settings.BASE_DIR, "templates", "base.html").read_text(encoding="utf-8")
        css = Path(settings.BASE_DIR, "static", "css", "style.css").read_text(encoding="utf-8")
        politica = Path(
            settings.BASE_DIR, "templates", "privacy", "policy.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("fonts.googleapis.com", base)
        self.assertNotIn("Google Fonts", politica)
        for peso in ("300", "400", "500", "600"):
            self.assertIsNotNone(finders.find(f"fonts/outfit-{peso}.ttf"))
            self.assertIn(f"outfit-{peso}.ttf", css)
