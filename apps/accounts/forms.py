from django import forms
from django.contrib.auth.forms import AuthenticationForm


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


class RegistrationForm(UserCreationForm):
    """Cadastro de novo usuario, com aceite explicito da politica (requisito 4.4)."""

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