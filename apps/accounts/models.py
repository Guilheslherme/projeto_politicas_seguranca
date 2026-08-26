from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Usuario da plataforma.

    O campo `password`, herdado de AbstractBaseUser, guarda a string completa
    do Argon2id: algoritmo, parametros, salt e hash (requisito 1.4).
    """

    email = models.EmailField("e-mail", unique=True)
    full_name = models.CharField("nome completo", max_length=150)

    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("equipe", default=False)

    two_factor_enabled = models.BooleanField("2FA ativo", default=False)

    date_joined = models.DateTimeField("cadastrado em", default=timezone.now)
    last_password_change = models.DateTimeField(
        "ultima troca de senha", null=True, blank=True
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
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
        super().set_password(raw_password)
        self.last_password_change = timezone.now()

    @property
    def hash_algorithm(self):
        return self.password.split("$")[0] if self.password else ""