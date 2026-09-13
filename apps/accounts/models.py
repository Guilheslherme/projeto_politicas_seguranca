import hashlib
import secrets
from binascii import unhexlify

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from .crypto import cifrar, decifrar, esta_cifrado
from .managers import UserManager


""""Modelo de usuário personalizado para o projeto, com suporte a autenticação por e-mail e 2FA."""

class User(AbstractBaseUser, PermissionsMixin):
    """Usuário do sistema, identificado pelo e-mail.
    Herda de AbstractBaseUser, que traz o campo de senha e toda a mecânica de
    hash e verificação, e de PermissionsMixin, que traz o sistema de permissões
    usado pelo painel administrativo.
 
    Só são coletados os dados necessários para autenticar e proteger a conta."""
   
    """ Identificador de login. É único, então o banco recusa duas contas com o
    mesmo endereço mesmo que a validação da aplicação falhe."""
    email = models.EmailField("e-mail", unique=True)

    full_name = models.CharField("nome completo", max_length=150)

     # Desativar a conta em vez de apagá-la preserva o histórico e permite
    # reverter. O Django recusa o login de contas inativas.
    is_active = models.BooleanField("ativo", default=True)

    # Dá acesso ao painel administrativo.
    is_staff = models.BooleanField("equipe", default=False)

    """ Espelha o estado da verificação em duas etapas. A informação verdadeira
     está no modelo TOTPDevice, mas este campo permite consultas rápidas. """
    two_factor_enabled = models.BooleanField("2FA ativo", default=False)

    date_joined = models.DateTimeField("cadastrado em", default=timezone.now)

    """ Registra quando a senha foi trocada pela última vez. Serve de base para
    política de expiração de senha e para a trilha de auditoria. """
    last_password_change = models.DateTimeField(
        "ultima troca de senha", null=True, blank=True
    )

    objects = UserManager()

    # Diz ao Django qual campo identifica a pessoa no login.
    USERNAME_FIELD = "email"

    # Campos pedidos além do e-mail e da senha no createsuperuser.
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["email"]

    def __str__(self):
        return self.email

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    def get_full_name(self):
        return self.full_name

    def set_password(self, raw_password):
        """Garante que a data da última troca de senha seja atualizada sempre que a senha for alterada.
        A senha em si é armazenada de forma segura usando o algoritmo de hash configurado (Argon2)."""

        super().set_password(raw_password)
        self.last_password_change = timezone.now()

    @property
    def hash_algorithm(self):
        return self.password.split("$")[0] if self.password else ""

"""Token de uso único para redefinição de senha (requisitos 2.2 a 2.5)."""

class PasswordResetToken(models.Model):
    """Autorização temporária para trocar a senha sem saber a senha antiga.

    O token em texto puro existe apenas dentro do link enviado por e-mail. No
    banco fica somente o resumo SHA-256 dele, então quem lesse esta tabela não
    conseguiria montar um link válido.
    """

    # 32 bytes = 256 bits de entropia, sorteados pelo gerador criptográfico do
    # sistema operacional. Adivinhar um token por tentativa e erro é inviável.
    TAMANHO_EM_BYTES = 32

    # Situações devolvidas por resolver(), usadas pela view para dar a resposta
    # certa a cada tipo de falha (requisito 2.5).
    SITUACAO_VALIDO = "VALIDO"
    SITUACAO_INEXISTENTE = "INEXISTENTE"
    SITUACAO_EXPIRADO = "EXPIRADO"
    SITUACAO_JA_USADO = "JA_USADO"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
        verbose_name="usuario",
    )

    """ Guarda o SHA-256 do token, nunca o token. São 64 caracteres em
    hexadecimal, tamanho fixo. Aqui o SHA-256 basta e o Argon2 seria
    contraproducente: o custo alto do Argon2 existe para proteger segredos
    fracos, como senhas escolhidas por pessoas, e este valor já nasce com 256
    bits aleatórios. """
    token_hash = models.CharField("hash do token", max_length=64, unique=True)

    created_at = models.DateTimeField("criado em", auto_now_add=True)

    # Prazo definido em PASSWORD_RESET_TOKEN_TIMEOUT, gravado no próprio
    # registro para que mudar a configuração depois não estenda links já
    # enviados.
    expires_at = models.DateTimeField("expira em")

    # Preenchido quando o token é gasto para trocar a senha (requisito 2.4).
    used_at = models.DateTimeField("usado em", null=True, blank=True)

    """ Preenchido quando o token deixa de valer sem ter sido usado, porque a
    pessoa pediu um link novo ou porque outro token da mesma conta foi gasto.
    É um campo separado de used_at para que o log distinga quem trocou a senha
    de quem simplesmente pediu o link duas vezes. """
    invalidated_at = models.DateTimeField("invalidado em", null=True, blank=True)

    requested_ip = models.GenericIPAddressField(
        "endereco da solicitacao", null=True, blank=True
    )

    class Meta:
        verbose_name = "token de recuperacao de senha"
        verbose_name_plural = "tokens de recuperacao de senha"
        ordering = ["-created_at"]

    def __str__(self):
        return f"token de {self.user.email} criado em {self.created_at:%d/%m/%Y %H:%M}"

    @staticmethod
    def calcular_hash(token_puro):
        """Converte o token do link no valor que fica gravado no banco."""
        return hashlib.sha256(token_puro.encode("utf-8")).hexdigest()

    @classmethod
    def emitir(cls, user, ip=None):
        """Cria um token novo e devolve a dupla (registro, token em texto puro).

        O token puro é devolvido só nesta chamada, para ser colocado no link do
        e-mail. Depois disso não há como recuperá-lo a partir do banco.
        """
        # Um link novo cancela os anteriores: se a pessoa pediu de novo, o link
        # antigo pode ter ido parar na caixa de entrada errada.
        cls.objects.filter(
            user=user, used_at__isnull=True, invalidated_at__isnull=True
        ).update(invalidated_at=timezone.now())

        token_puro = secrets.token_urlsafe(cls.TAMANHO_EM_BYTES)
        registro = cls.objects.create(
            user=user,
            token_hash=cls.calcular_hash(token_puro),
            expires_at=timezone.now() + settings.PASSWORD_RESET_TOKEN_TIMEOUT,
            requested_ip=ip,
        )
        return registro, token_puro

    @classmethod
    def resolver(cls, token_puro):
        """Localiza o token do link e diz em que situação ele está.

        Devolve a dupla (registro, situacao). O registro vem como None quando
        nenhum token corresponde ao valor recebido.
        """
        # A busca é feita pelo hash, então o valor do link nunca é comparado
        # diretamente com nada gravado no banco.
        registro = cls.objects.filter(token_hash=cls.calcular_hash(token_puro)).first()

        if registro is None:
            return None, cls.SITUACAO_INEXISTENTE
        if registro.used_at is not None:
            return registro, cls.SITUACAO_JA_USADO
        # Um token cancelado por um pedido mais novo responde como inexistente:
        # para quem clicou, o link simplesmente não vale mais.
        if registro.invalidated_at is not None:
            return registro, cls.SITUACAO_INEXISTENTE
        if registro.expires_at <= timezone.now():
            return registro, cls.SITUACAO_EXPIRADO
        return registro, cls.SITUACAO_VALIDO

    def marcar_como_usado(self):
        """Gasta o token e cancela os demais tokens pendentes da mesma conta."""
        agora = timezone.now()
        self.used_at = agora
        self.save(update_fields=["used_at"])

        PasswordResetToken.objects.filter(
            user=self.user, used_at__isnull=True, invalidated_at__isnull=True
        ).update(invalidated_at=agora)


"""Segredo do 2FA cifrado em repouso (requisitos 3.4 e 3.5)."""

def contexto_do_segredo_2fa(user_id):
    """Contexto de autenticação usado ao cifrar o segredo de uma conta.

    Fica em função própria porque a migração que cifra os segredos já
    existentes precisa produzir exatamente o mesmo valor.
    """
    return f"totp:{user_id}"


class EncryptedTOTPDevice(TOTPDevice):
    """Dispositivo TOTP que guarda o segredo cifrado com AES-256-GCM.

    O django-otp grava o segredo do aplicativo autenticador em texto puro. Esse
    segredo é o dado mais perigoso do banco: com ele, qualquer pessoa gera os
    mesmos códigos de 6 dígitos que o celular do usuário, e a segunda etapa do
    login deixa de proteger alguma coisa. Um vazamento do banco, de um backup
    ou de uma consulta por injeção de SQL entregaria o 2FA de todas as contas.

    É um modelo proxy: usa a mesma tabela do django-otp, sem duplicar dados. Só
    muda o que entra e o que sai do campo "key".
    """

    class Meta:
        proxy = True
        verbose_name = "dispositivo 2FA cifrado"
        verbose_name_plural = "dispositivos 2FA cifrados"

    def save(self, *args, **kwargs):
        # O django-otp sorteia o segredo em hexadecimal na criação. Antes de ir
        # para o banco ele é convertido de volta para os 20 bytes originais e
        # cifrado. Um segredo que já está cifrado passa direto, então salvar o
        # mesmo dispositivo de novo não cifra duas vezes.
        if not esta_cifrado(self.key):
            self.key = cifrar(unhexlify(self.key), contexto_do_segredo_2fa(self.user_id))
        super().save(*args, **kwargs)

    @property
    def bin_key(self):
        """Segredo decifrado, apenas na memória e apenas quando é usado.

        É a única propriedade que o django-otp usa para ler o segredo, tanto ao
        conferir um código quanto ao montar o QR Code. Sobrescrevê-la basta para
        que todo o resto da biblioteca funcione sem saber que existe cifragem.
        """
        return decifrar(self.key, contexto_do_segredo_2fa(self.user_id))
