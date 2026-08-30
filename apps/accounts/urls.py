from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path("entrar/", views.TwoFactorLoginView.as_view(), name="login"),
    path("sair/", views.SecureLogoutView.as_view(), name="logout"),
    path("perfil/", views.profile, name="profile"),
    path("verificacao/", views.otp_verify, name="otp_verify"),
    path("verificacao/ativar/", views.otp_setup, name="otp_setup"),
    path("verificacao/desativar/", views.otp_disable, name="otp_disable"),
]