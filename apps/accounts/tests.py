import importlib
import os
import time
import urllib.error
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from axes.models import AccessAttempt
from axes.utils import reset

from apps.audit.models import PasswordResetLog
from apps.privacy.models import ConsentRecord

from .crypto import FalhaNaDecifragem, cifrar, decifrar
from .emails import FalhaNoEnvio, enviar_link_de_recuperacao
from .models import EncryptedTOTPDevice, PasswordResetToken

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

    def test_fluxo_completo_troca_a_senha(self):
        _, link = self.pedir_link()
        self.client.post(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.SENHA_NOVA))
        self.assertFalse(self.user.check_password(SENHA))

    def test_senha_redefinida_continua_em_argon2id(self):
        _, link = self.pedir_link()
        self.client.post(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        self.user.refresh_from_db()
        # A senha nova passa pelo mesmo hasher do cadastro, e não por um
        # caminho paralelo mais fraco.
        self.assertTrue(self.user.password.startswith("argon2$argon2id$"))

    def test_senha_nova_fraca_e_recusada(self):
        _, link = self.pedir_link()
        self.client.post(link, {"new_password1": "123456", "new_password2": "123456"})

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
        self.client.post(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        registro = PasswordResetToken.objects.get()
        self.assertIsNotNone(registro.used_at)

    def test_mesmo_link_nao_serve_duas_vezes(self):
        _, link = self.pedir_link()
        self.client.post(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )

        terceira = "TerceiraSenhaBoa2026"
        resposta = self.client.post(
            link, {"new_password1": terceira, "new_password2": terceira}
        )

        self.assertEqual(resposta.status_code, 400)
        self.user.refresh_from_db()
        # Continua valendo a senha da primeira troca.
        self.assertTrue(self.user.check_password(self.SENHA_NOVA))

    def test_pedido_novo_cancela_o_link_anterior(self):
        _, primeiro_link = self.pedir_link()
        self.pedir_link()

        resposta = self.client.post(
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

        resposta = self.client.post(
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
        self.client.post(
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
        self.client.post(
            link, {"new_password1": self.SENHA_NOVA, "new_password2": self.SENHA_NOVA}
        )
        self.client.post(
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
