from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

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