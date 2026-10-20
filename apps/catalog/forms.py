"""Formulários do acervo que recebem dados enviados pelo titular."""

from django import forms


class ConsentimentoMateriaisForm(forms.Form):
    """Valida o material selecionado e o aceite antes de gravar o consentimento."""

    material = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.HiddenInput,
    )
    aceite = forms.BooleanField(
        required=True,
        error_messages={"required": "Marque a caixa para registrar seu consentimento."},
        widget=forms.CheckboxInput(attrs={"id": "aceite-materiais"}),
    )
