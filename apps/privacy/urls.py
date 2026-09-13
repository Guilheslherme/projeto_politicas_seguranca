#rotas da privacidade: politica, aceite e os direitos do titular previstos no Art. 18 da LGPD
from django.urls import path

from . import views

app_name = "privacy"

urlpatterns = [
    path("politica/", views.privacy_policy, name="policy"),
    path("consentimento/", views.consent, name="consent"),
    path("meus-dados/", views.my_data, name="my_data"),
    path("meus-dados/exportar/", views.export_data, name="export_data"),
    path("excluir-conta/", views.delete_account, name="delete_account"),
]
