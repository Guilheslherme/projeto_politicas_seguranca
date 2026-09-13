from django import forms

#aqui o titular aceita a versao atual da politica, quando ainda nao aceitou
class ConsentForm(forms.Form):
    """Aceite explícito da versão vigente da Política de Privacidade."""

    # Caixa desmarcada por padrão e obrigatória. O consentimento precisa ser
    # uma manifestação ativa (Art. 5º, XII): uma caixa já marcada, ou o simples
    # uso do site, não valeria como consentimento.
    accept = forms.BooleanField(
        label="Li e aceito a Política de Privacidade",
        required=True,
    )


#aqui a pessoa confirma a senha antes de excluir a conta
class DeleteAccountForm(forms.Form):
    """Confirmação da exclusão da conta pela senha atual."""

    password = forms.CharField(
        label="Senha atual",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        # A exclusão é irreversível. Pedir a senha de novo impede que alguém que
        # encontre o computador com a sessão aberta apague a conta de outra
        # pessoa com um clique.
        senha = self.cleaned_data["password"]
        if not self.user.check_password(senha):
            raise forms.ValidationError("Senha incorreta.")
        return senha
