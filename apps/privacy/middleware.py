"""Exige consentimento vigente de quem está logado (requisitos 4.4 e 4.7)."""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .models import ConsentRecord


class ConsentRequiredMiddleware:
    """Leva à tela de aceite quem está logado sem consentimento vigente.

    Cobre três situações com a mesma regra: contas criadas antes de o aceite
    ser gravado, contas que aceitaram uma versão anterior da política e qualquer
    caminho que eventualmente crie conta sem passar pelo cadastro. Enquanto não
    houver aceite da versão atual, nenhuma página da conta é aberta.
    """

    # Rotas que precisam continuar acessíveis sem consentimento: a própria tela
    # de aceite, o texto da política que está sendo aceito, a saída e a exclusão
    # da conta — recusar a política não pode deixar a pessoa sem como ir embora.
    ROTAS_LIBERADAS = (
        "privacy:consent",
        "privacy:policy",
        "privacy:delete_account",
        "accounts:logout",
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self._caminhos_liberados = None

    def _liberado(self, caminho):
        if self._caminhos_liberados is None:
            self._caminhos_liberados = {reverse(nome) for nome in self.ROTAS_LIBERADAS}
        # O painel administrativo e os arquivos estáticos ficam fora da regra: o
        # primeiro tem controle de acesso próprio, e os segundos são públicos.
        return (
            caminho in self._caminhos_liberados
            or caminho.startswith("/admin/")
            or caminho.startswith(settings.STATIC_URL)
        )

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not self._liberado(request.path)
            and not ConsentRecord.tem_consentimento_vigente(request.user)
        ):
            return redirect("privacy:consent")
        return self.get_response(request)
