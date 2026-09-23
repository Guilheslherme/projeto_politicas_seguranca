"""Rotas do acervo: marcar sintomas e ver o que as fontes dizem."""

from django.urls import path

from . import views, views_conta

app_name = "catalog"

urlpatterns = [
    # Telas públicas: não exigem login e não gravam nada.
    path("sintomas/", views.selecionar_sintomas, name="sintomas"),
    path("sintomas/resultado/", views.resultado, name="resultado"),
    path("condicoes/<slug:slug>/", views.condicao, name="condicao"),

    # O que a conta oferece: exige login e grava no banco.
    path("materiais/", views_conta.meus_materiais, name="meus_materiais"),
    path("materiais/consentimento/", views_conta.consentimento, name="consentimento_materiais"),
    path("materiais/<int:material_id>/guardar/", views_conta.salvar, name="salvar_material"),
    path("materiais/<int:material_id>/remover/", views_conta.remover, name="remover_material"),
    path("materiais/revogar/", views_conta.revogar, name="revogar_materiais"),
]
