#importa as views e é a ordem das coisas que o sistema ira pedir (login, senha 2FA, logout etc.)
from django.conf import settings
from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "accounts"

# O prazo mostrado na tela sai da mesma configuração usada para emitir o token
# e para montar o e-mail. Escrever "30 minutos" no template criaria uma segunda
# fonte da mesma informação, que passaria a mentir no dia em que o prazo mudasse.
MINUTOS_DO_LINK = int(settings.PASSWORD_RESET_TOKEN_TIMEOUT.total_seconds() // 60)

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path("entrar/", views.TwoFactorLoginView.as_view(), name="login"),
    path("sair/", views.SecureLogoutView.as_view(), name="logout"),
    path("perfil/", views.profile, name="profile"),
    path("verificacao/", views.otp_verify, name="otp_verify"),
    path("verificacao/ativar/", views.otp_setup, name="otp_setup"),
    path("verificacao/desativar/", views.otp_disable, name="otp_disable"),

    # Recuperação de senha (requisito 2). As duas telas de aviso vêm antes da
    # rota do token: o Django testa os padrões na ordem, e "<str:token>"
    # engoliria "enviado" e "concluido" se viesse primeiro.
    path("recuperar/", views.password_reset_request, name="password_reset"),
    path(
        "recuperar/enviado/",
        TemplateView.as_view(
            template_name="accounts/password_reset_sent.html",
            extra_context={"minutos": MINUTOS_DO_LINK},
        ),
        name="password_reset_sent",
    ),
    path(
        "recuperar/concluido/",
        TemplateView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "recuperar/<str:token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
]
