import base64
import io
from datetime import datetime

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from .forms import EmailAuthenticationForm, OTPTokenForm, RegistrationForm
from .models import User


PENDING_USER_KEY = "pre_2fa_user_id"
PENDING_BACKEND_KEY = "pre_2fa_backend"
PENDING_TIME_KEY = "pre_2fa_started_at"


def _clear_pending(request):
    for key in (PENDING_USER_KEY, PENDING_BACKEND_KEY, PENDING_TIME_KEY):
        request.session.pop(key, None)


def _mascarar_email(email):
    # Mascara o e-mail para exibição na tela de verificação em duas etapas, sem
    # revelar o endereço completo.
    nome, _, dominio = email.partition("@")
    if len(nome) <= 2:
        visivel = nome[:1]
    else:
        visivel = nome[0] + "•" * (len(nome) - 2) + nome[-1]
    return f"{visivel}@{dominio}"


def _build_qr_data_uri(config_url):
    # Gera o QR code embutido na página, sem salvar arquivo no servidor.
    img = qrcode.make(config_url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def register_view(request):
    form = RegistrationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Conta criada com sucesso. Faça login para continuar.")
        return redirect("accounts:login")

    return render(request, "accounts/register.html", {"form": form})


class TwoFactorLoginView(LoginView):
    """Etapa 1: e-mail e senha."""

    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()

        if device is not None:
            # Senha correta, mas a sessão ainda não é criada.
            self.request.session[PENDING_USER_KEY] = user.pk
            self.request.session[PENDING_BACKEND_KEY] = getattr(
                user, "backend", "django.contrib.auth.backends.ModelBackend"
            )
            self.request.session[PENDING_TIME_KEY] = timezone.now().isoformat()
            return redirect("accounts:otp_verify")

        auth_login(self.request, user)
        messages.info(
            self.request,
            "Sua conta ainda não tem verificação em duas etapas. "
            "Recomendamos ativar agora.",
        )
        return redirect("accounts:profile")


def otp_verify(request):
    """Etapa 2: código de 6 dígitos. Só aqui a sessão é criada."""
    user_id = request.session.get(PENDING_USER_KEY)
    started_at = request.session.get(PENDING_TIME_KEY)

    if not user_id or not started_at:
        messages.error(request, "Sessão de verificação inválida. Faça login novamente.")
        return redirect("accounts:login")

    # A janela entre as duas etapas também expira.
    if timezone.now() - datetime.fromisoformat(started_at) > settings.TWO_FACTOR_PENDING_TIMEOUT:
        _clear_pending(request)
        messages.error(request, "Tempo esgotado para a verificação. Faça login novamente.")
        return redirect("accounts:login")

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        _clear_pending(request)
        return redirect("accounts:login")

    form = OTPTokenForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device and device.verify_token(form.cleaned_data["token"]):
            backend = request.session.get(PENDING_BACKEND_KEY)
            _clear_pending(request)
            auth_login(request, user, backend=backend)
            otp_login(request, device)
            return redirect("accounts:profile")

        form.add_error("token", "Código inválido ou expirado.")

    return render(
        request,
        "accounts/otp_verify.html",
        {"form": form, "email": _mascarar_email(user.email)},
    )


@login_required
def otp_setup(request):
    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(
            user=request.user, name="default", confirmed=False
        )

    form = OTPTokenForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        if device.verify_token(form.cleaned_data["token"]):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            request.user.two_factor_enabled = True
            request.user.save(update_fields=["two_factor_enabled"])
            otp_login(request, device)
            messages.success(request, "Verificação em duas etapas ativada.")
            return redirect("accounts:profile")
        form.add_error("token", "Código inválido. Confira o horário do seu celular.")

    return render(
        request,
        "accounts/otp_setup.html",
        {
            "form": form,
            "qr_data_uri": _build_qr_data_uri(device.config_url),
            "secret_url": device.config_url,
        },
    )


@login_required
def otp_disable(request):
    if request.method == "POST":
        TOTPDevice.objects.filter(user=request.user).delete()
        request.user.two_factor_enabled = False
        request.user.save(update_fields=["two_factor_enabled"])
        messages.warning(request, "Verificação em duas etapas desativada.")
    return redirect("accounts:profile")


@login_required
def profile(request):
    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    return render(
        request,
        "accounts/profile.html",
        {
            "has_2fa": device is not None,
            "session_expiry": request.session.get_expiry_date(),
            "hash_algorithm": request.user.hash_algorithm,
            "is_verified": request.user.is_verified(),
        },
    )


class SecureLogoutView(LogoutView):
    """O logout do Django apaga a sessão do banco, não só o cookie."""

    next_page = reverse_lazy("home")