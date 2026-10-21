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


class DesativarDoisFatoresForm(forms.Form):
    """Confirmação forte para desligar o 2FA: senha e código (risco R12).

    Desligar o 2FA tira a proteção que impede quem tem só a senha de entrar.
    Pedir os dois fatores de novo impede que alguém com a sessão aberta de
    outra pessoa faça isso com um clique.
    """

    password = forms.CharField(
        label="Senha atual",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    codigo = forms.CharField(
        label="Código do aplicativo ou código de reserva",
        max_length=16,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        # Importado aqui para evitar import circular com models e views.
        from . import codigos_reserva
        from .models import EncryptedTOTPDevice

        dados = super().clean()
        senha, codigo = dados.get("password"), (dados.get("codigo") or "").strip()
        if not senha or not codigo:
            return dados

        # A mesma mensagem para senha e código errados: dizer qual dos dois
        # falhou ajudaria quem está tentando adivinhar.
        erro = forms.ValidationError("Senha ou código incorretos.")
        if not self.user.check_password(senha):
            raise erro

        if codigo.isdigit() and len(codigo) == 6:
            device = EncryptedTOTPDevice.objects.filter(user=self.user, confirmed=True).first()
            if device is None or not device.verify_token(codigo):
                raise erro
        elif codigos_reserva.usar_codigo(self.user, codigo) is None:
            raise erro
        return dados


class CodigoReservaForm(forms.Form):
    """Código de reserva, para quem está sem o celular (risco R05)."""

    # "ABCDE-FGHJK": 10 símbolos, com ou sem o hífen e os espaços.
    codigo_reserva = forms.CharField(
        label="Código de reserva",
        max_length=16,
        widget=forms.TextInput(
            attrs={"autocomplete": "off", "autocapitalize": "characters", "placeholder": "ABCDE-FGHJK"}
        ),
    )


from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse
from django.utils.html import format_html

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # O aceite só vale se a pessoa tiver como ler o que está aceitando
        # (Art. 8º e 9º da LGPD). O link abre a política em outra aba para não
        # perder o que já foi preenchido.
        self.fields["accept_privacy_policy"].help_text = format_html(
            '<a href="{}" target="_blank" rel="noopener">Ler a Política de Privacidade</a>',
            reverse("privacy:policy"),
        )

    def clean_email(self):
        # Risco R08: o formulário não diz mais se o e-mail já tem conta. A
        # mensagem "Ja existe uma conta com este e-mail" deixava qualquer um
        # testar endereços. Quem decide o que fazer com e-mail repetido é a
        # view, que responde igual nos dois casos.
        return self.cleaned_data["email"].lower().strip()

    def validate_unique(self):
        # O ModelForm também acusaria o e-mail repetido, pelo unique=True do
        # modelo. A unicidade continua garantida pelo banco: a view só cria a
        # conta quando o endereço está livre.
        exclude = self._get_validation_exclusions()
        exclude.add("email")
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as erro:
            self._update_errors(erro)

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
