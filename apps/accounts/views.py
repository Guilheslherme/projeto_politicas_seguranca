import base64
import io
from datetime import datetime

import qrcode
from axes.helpers import get_client_ip_address
from axes.utils import reset as axes_reset
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django_otp import login as otp_login

from apps.audit.models import AuthEvent, PasswordResetLog

# O login e o logout entram na trilha sozinhos, por sinal do Django. O que o
# django-otp faz não dispara sinal nenhum, então os eventos do segundo fator e
# do cadastro são gravados aqui, na mão (requisitos 5.1 e 5.2).
from apps.audit.signals import registrar_evento
from apps.privacy.models import ConsentRecord

from .emails import FalhaNoEnvio, enviar_link_de_recuperacao
from .forms import (
    EmailAuthenticationForm,
    NewPasswordForm,
    OTPTokenForm,
    PasswordResetRequestForm,
    RegistrationForm,
)
# EncryptedTOTPDevice no lugar do TOTPDevice do django-otp: mesma tabela, mas
# o segredo do autenticador sai cifrado com AES-256-GCM (requisito 3.4).
from .models import EncryptedTOTPDevice, PasswordResetToken, User

#nesta pagina que acontece o 2FA com TOTP, cadastro, a ativação e desativação dos 2 fatores e mostra o perfil do usuario.
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
        # A conta e o registro do aceite nascem juntos. Se a gravação do aceite
        # falhar, a conta também não é criada: não existe conta sem a prova do
        # consentimento que a autorizou (requisito 4.4).
        with transaction.atomic():
            user = form.save()
            ConsentRecord.registrar_aceite(user)

        # Fora da transação, de propósito: o evento diz que a conta foi criada,
        # então só deve existir depois que a criação foi mesmo confirmada.
        registrar_evento(request, AuthEvent.Event.CADASTRO, user=user)

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
        device = EncryptedTOTPDevice.objects.filter(user=user, confirmed=True).first()

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
        device = EncryptedTOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device and device.verify_token(form.cleaned_data["token"]):
            backend = request.session.get(PENDING_BACKEND_KEY)
            _clear_pending(request)
            auth_login(request, user, backend=backend)
            otp_login(request, device)

            # Depois do auth_login, então a trilha mostra a ordem real dos
            # fatos: a sessão nasce e em seguida o segundo fator é confirmado
            # nela. O LOGIN_OK logo antes deste registro vem do sinal.
            registrar_evento(request, AuthEvent.Event.OTP_OK, user=user)
            return redirect("accounts:profile")

        # Requisito 5.2. Aqui não existe sinal do Django para aproveitar: a
        # senha já tinha sido aceita, e quem recusou o código foi o django-otp.
        # Sem esta linha, uma sequência de códigos errados não deixaria rastro
        # nenhum, que é exatamente o padrão que a análise precisa enxergar.
        registrar_evento(request, AuthEvent.Event.OTP_FALHOU, user=user)
        form.add_error("token", "Código inválido ou expirado.")

    return render(
        request,
        "accounts/otp_verify.html",
        {"form": form, "email": _mascarar_email(user.email)},
    )


@login_required
def otp_setup(request):
    device = EncryptedTOTPDevice.objects.filter(user=request.user, confirmed=False).first()
    if device is None:
        device = EncryptedTOTPDevice.objects.create(
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
            registrar_evento(request, AuthEvent.Event.OTP_ATIVADO, user=request.user)
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
        EncryptedTOTPDevice.objects.filter(user=request.user).delete()
        request.user.two_factor_enabled = False
        request.user.save(update_fields=["two_factor_enabled"])

        # Desligar o segundo fator enfraquece a conta, então o evento fica
        # registrado: se a conta for invadida depois, a trilha mostra se a
        # proteção foi desligada antes e por qual endereço.
        registrar_evento(request, AuthEvent.Event.OTP_DESATIVADO, user=request.user)

        messages.warning(request, "Verificação em duas etapas desativada.")
    return redirect("accounts:profile")


@login_required
def profile(request):
    device = EncryptedTOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    return render(
        request,
        "accounts/profile.html",
        {
            "has_2fa": device is not None,
            "session_expiry": request.session.get_expiry_date(),
            "hash_algorithm": request.user.hash_algorithm,
            # Só o prefixo do valor gravado, que nomeia o algoritmo. O texto
            # cifrado em si não vai para a tela.
            "totp_secret_format": device.key.split("$")[0] if device else "",
            "is_verified": request.user.is_verified(),
        },
    )


class SecureLogoutView(LogoutView):
    """O logout do Django apaga a sessão do banco, não só o cookie."""

    next_page = reverse_lazy("home")

# ---------------------------------------------------------------------------
# Recuperação de senha (requisitos 2.1 a 2.7)
# ---------------------------------------------------------------------------

# Cada situação de token recusado vira um evento no log e uma explicação na
# tela. Um token cancelado por pedido mais novo entra como inexistente: para
# quem clicou, o link simplesmente não vale mais.
FALHAS_DO_TOKEN = {
    PasswordResetToken.SITUACAO_INEXISTENTE: (
        PasswordResetLog.Event.TOKEN_INVALIDO,
        "Este link não é válido. Ele pode ter sido substituído por um pedido "
        "mais recente ou copiado pela metade.",
    ),
    PasswordResetToken.SITUACAO_EXPIRADO: (
        PasswordResetLog.Event.TOKEN_EXPIRADO,
        "Este link expirou. Por segurança, cada link vale por tempo limitado.",
    ),
    PasswordResetToken.SITUACAO_JA_USADO: (
        PasswordResetLog.Event.TOKEN_JA_USADO,
        "Este link já foi usado para trocar a senha. Cada link serve uma vez só.",
    ),
}


def _excedeu_o_limite_de_pedidos(user):
    """Diz se aquela conta já esgotou os pedidos permitidos na janela.

    Precisa ser consultada antes de registrar o pedido atual, senão ele entra
    na própria contagem e o limite dispara um pedido cedo demais.

    A contagem é por conta, e não pelo endereço digitado, porque o log não
    guarda mais o e-mail. Endereço sem conta não precisa de limite: nenhuma
    mensagem é enviada nesse caso, então não há caixa de entrada para inundar.
    """
    # A contagem sai da própria trilha de auditoria, sem precisar de outra
    # tabela só para isso.
    desde = timezone.now() - settings.PASSWORD_RESET_REQUEST_WINDOW
    anteriores = PasswordResetLog.objects.filter(
        event=PasswordResetLog.Event.SOLICITADO,
        user=user,
        created_at__gte=desde,
    ).count()
    return anteriores >= settings.PASSWORD_RESET_MAX_REQUESTS


def password_reset_request(request):
    """Etapa 1: a pessoa informa o e-mail e recebe o link."""
    form = PasswordResetRequestForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        # A checagem vem antes do registro, e o registro vem antes de qualquer
        # desvio: todo pedido entra na trilha de auditoria, inclusive os
        # recusados pelo limite (requisito 2.6). Um pedido para endereço sem
        # conta é registrado com usuário nulo.
        excedeu = user is not None and _excedeu_o_limite_de_pedidos(user)

        PasswordResetLog.registrar(
            request, PasswordResetLog.Event.SOLICITADO, user
        )

        if excedeu:
            PasswordResetLog.registrar(
                request,
                PasswordResetLog.Event.LIMITE_EXCEDIDO,
                user,
                detail=f"acima de {settings.PASSWORD_RESET_MAX_REQUESTS} pedidos na janela",
            )
        elif user is not None:
            _, token_puro = PasswordResetToken.emitir(
                user, ip=get_client_ip_address(request)
            )
            link = settings.APP_BASE_URL.rstrip("/") + reverse(
                "accounts:password_reset_confirm", args=[token_puro]
            )
            try:
                enviar_link_de_recuperacao(user, link)
            except FalhaNoEnvio as erro:
                # O token continua válido: a pessoa pode pedir outro link, e o
                # anterior será cancelado na hora da emissão.
                # A mensagem de FalhaNoEnvio é montada pelo próprio projeto e
                # traz apenas o motivo técnico, sem o corpo da resposta do
                # Brevo, que costuma repetir o endereço do destinatário.
                PasswordResetLog.registrar(
                    request,
                    PasswordResetLog.Event.EMAIL_FALHOU,
                    user,
                    detail=str(erro),
                )
            else:
                PasswordResetLog.registrar(
                    request, PasswordResetLog.Event.EMAIL_ENVIADO, user
                )

        # A resposta é a mesma nos quatro caminhos acima, inclusive quando o
        # e-mail não existe ou o envio falhou. Uma resposta diferente para conta
        # existente revelaria quem tem cadastro no sistema, que é o mesmo motivo
        # da mensagem genérica do login.
        return redirect("accounts:password_reset_sent")

    return render(request, "accounts/password_reset_request.html", {"form": form})


def password_reset_confirm(request, token):
    """Etapa 2: o link é conferido e a senha nova é definida."""
    registro, situacao = PasswordResetToken.resolver(token)

    if situacao != PasswordResetToken.SITUACAO_VALIDO:
        evento, mensagem = FALHAS_DO_TOKEN[situacao]
        # O token recusado não entra no log: registrar o valor do link daria a
        # quem lesse a trilha exatamente o que falta para usá-lo, no caso de um
        # link ainda dentro do prazo. O evento e a conta bastam para auditar.
        PasswordResetLog.registrar(
            request, evento, registro.user if registro else None
        )
        # A tela de erro não traz o formulário de senha nova: um link recusado
        # não abre caminho para trocar coisa alguma (requisito 2.5).
        return render(
            request,
            "accounts/password_reset_invalid.html",
            {"mensagem": mensagem},
            status=400,
        )

    form = NewPasswordForm(registro.user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        # Trocar a senha muda o hash de sessão do Django, então toda sessão
        # aberta daquela conta deixa de valer — inclusive a de quem tivesse
        # entrado com a senha antiga.
        form.save()

        # A ordem importa: o token é gasto depois da troca, e não antes dela.
        # Se a gravação da senha falhasse, o token continuaria valendo.
        registro.marcar_como_usado()

        # Quem esqueceu a senha costuma ter errado várias vezes antes de pedir
        # o link, e ficaria bloqueado pelo axes logo após redefini-la. Liberar
        # aqui é seguro: só chega neste ponto quem provou ter acesso à caixa de
        # entrada da conta.
        axes_reset(username=registro.user.email)

        PasswordResetLog.registrar(
            request, PasswordResetLog.Event.SENHA_REDEFINIDA, registro.user
        )
        return redirect("accounts:password_reset_done")

    return render(request, "accounts/password_reset_confirm.html", {"form": form})
