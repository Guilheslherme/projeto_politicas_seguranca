from django import forms
from django.contrib.auth.forms import AuthenticationForm

#essa parte se refere ao login, sendo necessario apenas o email     
class EmailAuthenticationForm(AuthenticationForm):
    """Login por e-mail em vez de nome de usuario."""

    username = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        # Mensagem generica: nao revela se o e-mail existe no sistema,
        # o que impediria enumeracao de contas.
        "invalid_login": "E-mail ou senha incorretos.",
    }

#aqui pede o codigo de 6 digitos 
class OTPTokenForm(forms.Form):
    """Codigo de 6 digitos do aplicativo autenticador."""

    token = forms.CharField(
        label="Codigo de verificacao",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]*",
                "placeholder": "000000",
            }
        ),
    )

    def clean_token(self):
        token = self.cleaned_data["token"].strip()
        if not token.isdigit():
            raise forms.ValidationError("O codígo deve conter apenas números.")
        return token


from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User

#esta parte e sobre o cadastro de um novo usuario, que apenas pede o nome e o email, e verifica se ja tem alguem cadastrado com aquele email.
class RegistrationForm(UserCreationForm):
    """Cadastro de novo usuario. Aceita apenas e-mail e nome completo."""

    email = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    full_name = forms.CharField(label="Nome completo", max_length=150)
    accept_privacy_policy = forms.BooleanField(
        label="Li e aceito a Politica de Privacidade e o tratamento dos meus dados",
        required=True,
    )

    class Meta:
        model = User
        fields = ("email", "full_name")

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ja existe uma conta com este e-mail.")
        return email

from django.contrib.auth.forms import SetPasswordForm

#aqui e a recuperacao de senha: primeiro pede so o e-mail, depois pede a senha nova
class PasswordResetRequestForm(forms.Form):
    """Solicitacao do link de recuperacao. Pede apenas o e-mail."""

    email = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def clean_email(self):
        # Mesma normalizacao do cadastro, para que quem digitou Joao@Gmail.com
        # encontre a conta criada como joao@gmail.com.
        return self.cleaned_data["email"].lower().strip()


class NewPasswordForm(SetPasswordForm):
    """Definicao da senha nova, ao final do fluxo de recuperacao.

    Herda de SetPasswordForm para reaproveitar a conferencia de
    AUTH_PASSWORD_VALIDATORS e a gravacao pelo set_password. Sao os mesmos
    validadores do cadastro: a senha escolhida aqui passa pelo minimo de 10
    caracteres, pela lista de senhas comuns e pelo hash Argon2id.
    """

    error_messages = {
        **SetPasswordForm.error_messages,
        "password_mismatch": "As duas senhas nao conferem.",
    }
