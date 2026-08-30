from django.contrib.auth.base_user import BaseUserManager

"""
Criação de usuários e superusuários.
 
Como o modelo de usuário foi trocado para usar e-mail no lugar de nome de
usuário, o gerenciador de usuários também precisa ser personalizado. Usando e-mail como identificador único.
"""

class UserManager(BaseUserManager):
    """Gerenciador de usuários que identifica a conta pelo e-mail."""

    # Permite que as migrações usem este gerenciador ao criar usuários.
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("O e-mail e obrigatorio.")

        # Padroniza o domínio para minúsculas. Sem isso, joao@Gmail.com e
        # joao@gmail.com seriam tratados como contas diferentes.
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)

        # É aqui que a senha vira hash Argon2id. O valor em texto puro existe
        # apenas na memória, durante esta chamada, e não é gravado em lugar
        # nenhum.
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Cria uma conta comum, sem acesso ao painel administrativo."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Cria a conta administrativa usada pelo comando createsuperuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)