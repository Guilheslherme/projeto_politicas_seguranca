import base64
import io
import logging
from datetime import datetime

import qrcode
from axes.helpers import get_client_ip_address
from axes.utils import reset as axes_reset
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_otp import login as otp_login
from django_ratelimit.core import is_ratelimited

from apps.audit.models import AuthEvent, PasswordResetLog

# O login e o logout entram na trilha sozinhos, por sinal do Django. O que o
# django-otp faz não dispara sinal nenhum, então os eventos do segundo fator e
# do cadastro são gravados aqui, na mão (requisitos 5.1 e 5.2).
from apps.audit.signals import registrar_evento
from apps.privacy.models import ConsentRecord

from . import codigos_reserva
from .emails import (
    FalhaNoEnvio,
    enviar_aviso_de_conta_existente,
    enviar_link_de_confirmacao,
    enviar_link_de_recuperacao,
)
from .limites import confirmacao_bloqueada, limitar, registrar_confirmacao_errada
from .forms import (
    CodigoReservaForm,
    DesativarDoisFatoresForm,
    EmailAuthenticationForm,
    NewPasswordForm,
    OTPTokenForm,
    PasswordResetRequestForm,
    RegistrationForm,
)
# EncryptedTOTPDevice no lugar do TOTPDevice do django-otp: mesma tabela, mas
# o segredo do autenticador sai cifrado com AES-256-GCM (requisito 3.4).
from .models import EmailConfirmationToken, EncryptedTOTPDevice, PasswordResetToken, User

logger = logging.getLogger(__name__)

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


@limitar("cadastro")
def register_view(request):
    """Cadastro que responde igual para e-mail novo ou já cadastrado (R08).

    Nos dois casos a pessoa vai para a mesma tela, "confira seu e-mail". Com
    e-mail novo, a conta nasce inativa e recebe o link de confirmação. Com
    e-mail que já tem conta, nada é criado, e o dono do endereço recebe um
    aviso. Só quem abre a caixa de entrada descobre qual dos dois aconteceu.
    """
    form = RegistrationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        existente = User.objects.filter(email__iexact=form.cleaned_data["email"]).first()

        if existente is None:
            # A conta e o registro do aceite nascem juntos. Se a gravação do
            # aceite falhar, a conta também não é criada: não existe conta sem
            # a prova do consentimento que a autorizou (requisito 4.4).
            with transaction.atomic():
                user = form.save(commit=False)
                user.is_active = False
                user.save()
                ConsentRecord.registrar_aceite(user)

            # Fora da transação, de propósito: o evento diz que a conta foi
            # criada, então só deve existir depois que a criação foi confirmada.
            registrar_evento(request, AuthEvent.Event.CADASTRO, user=user)
            _enviar_confirmacao(user)
        else:
            # O cadastro novo calcula um Argon2id ao gravar a senha. Calcular
            # um aqui também evita que o tempo de resposta denuncie o caso.
            make_password(form.cleaned_data["password1"])
            _tratar_cadastro_repetido(request, existente)

        return redirect("accounts:register_sent")

    return render(request, "accounts/register.html", {"form": form})


def _enviar_confirmacao(user):
    token_puro = EmailConfirmationToken.emitir(user)
    link = settings.APP_BASE_URL.rstrip("/") + reverse(
        "accounts:confirm_email", args=[token_puro]
    )
    try:
        enviar_link_de_confirmacao(user, link)
    except FalhaNoEnvio as erro:
        # A tela não muda: avisar a falha só para e-mail novo revelaria o caso.
        # Quem não recebeu pode se cadastrar de novo, e um link novo é enviado.
        logger.warning("Falha ao enviar a confirmacao de e-mail da conta %s: %s", user.pk, erro)


def _tratar_cadastro_repetido(request, existente):
    if not existente.is_active:
        # Conta que nunca foi confirmada: manda um link novo. Conta desativada
        # depois de usada (já tem last_login) continua como está.
        if existente.last_login is None:
            _enviar_confirmacao(existente)
        return

    # Um aviso por hora por conta, para o formulário não virar uma forma de
    # lotar a caixa de entrada de alguém.
    if is_ratelimited(
        request, group="cadastro:aviso", key=lambda grupo, req: str(existente.pk),
        rate="1/h", method="POST", increment=True,
    ):
        return

    link = settings.APP_BASE_URL.rstrip("/") + reverse("accounts:password_reset")
    try:
        enviar_aviso_de_conta_existente(existente, link)
    except FalhaNoEnvio as erro:
        logger.warning("Falha ao enviar aviso de cadastro repetido da conta %s: %s", existente.pk, erro)


def confirm_email(request, token):
    """Ativa a conta pelo link do e-mail. O token vale uma vez só."""
    user = EmailConfirmationToken.consumir(token)
    if user is None:
        messages.error(
            request,
            "Este link de confirmação não vale mais. Cadastre-se de novo com o "
            "mesmo e-mail para receber um link novo.",
        )
        return redirect("accounts:register")

    messages.success(request, "E-mail confirmado. Agora você já pode entrar.")
    return redirect("accounts:login")


@method_decorator(limitar("login"), name="dispatch")
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

        if user.is_staff:
            # Risco R05: conta da equipe sem 2FA não entra. Se entrasse, quem
            # tivesse só a senha poderia ativar o 2FA no próprio celular e
            # abrir o painel administrativo.
            registrar_evento(
                self.request,
                AuthEvent.Event.LOGIN_FALHOU,
                user=user,
                detail="conta da equipe sem 2FA: entrada recusada",
            )
            form.add_error(
                None,
                "Contas da equipe só entram com a verificação em duas etapas "
                "ativa. Fale com quem administra o projeto.",
            )
            return self.form_invalid(form)

        primeiro_login = user.last_login is None
        auth_login(self.request, user)

        if primeiro_login:
            # Convite no primeiro acesso: a pessoa cai direto na tela de
            # ativação, que tem a opção de deixar para depois.
            messages.info(
                self.request,
                "Bem-vindo! Proteja sua conta com a verificação em duas etapas: "
                "leva um minuto.",
            )
            return redirect("accounts:otp_setup")

        messages.info(
            self.request,
            "Sua conta ainda não tem verificação em duas etapas. "
            "Recomendamos ativar agora.",
        )
        return redirect("accounts:profile")


@limitar("otp")
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

    usando_reserva = request.method == "POST" and "codigo_reserva" in request.POST
    form = OTPTokenForm(request.POST if request.method == "POST" and not usando_reserva else None)
    form_reserva = CodigoReservaForm(request.POST if usando_reserva else None)

    if usando_reserva and form_reserva.is_valid():
        # Risco R05: quem perdeu o celular entra com um dos códigos de
        # reserva, que vale uma vez só e é apagado aqui mesmo.
        device = codigos_reserva.usar_codigo(user, form_reserva.cleaned_data["codigo_reserva"])
        if device is not None:
            _concluir_login(request, user, device, detalhe="codigo de reserva")
            messages.warning(
                request,
                f"Você entrou com um código de reserva. Restam "
                f"{codigos_reserva.restantes(user)}. Gere novos no seu perfil "
                "se estiver acabando.",
            )
            return redirect("accounts:profile")
        registrar_evento(request, AuthEvent.Event.OTP_FALHOU, user=user, detail="codigo de reserva")
        form_reserva.add_error("codigo_reserva", "Código de reserva inválido ou já usado.")

    elif request.method == "POST" and form.is_valid():
        device = EncryptedTOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device and device.verify_token(form.cleaned_data["token"]):
            _concluir_login(request, user, device)
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
        {
            "form": form,
            "form_reserva": form_reserva,
            "reserva_aberta": usando_reserva,
            "email": _mascarar_email(user.email),
        },
    )


def _concluir_login(request, user, device, detalhe=""):
    """Cria a sessão depois do segundo fator, por código TOTP ou de reserva."""
    backend = request.session.get(PENDING_BACKEND_KEY)
    _clear_pending(request)
    auth_login(request, user, backend=backend)
    otp_login(request, device)
    if isinstance(device, EncryptedTOTPDevice):
        device.recifrar_se_preciso()

    # Depois do auth_login, então a trilha mostra a ordem real dos fatos: a
    # sessão nasce e em seguida o segundo fator é confirmado nela. O LOGIN_OK
    # logo antes deste registro vem do sinal.
    registrar_evento(request, AuthEvent.Event.OTP_OK, user=user, detail=detalhe)


@login_required
@never_cache
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
            return _mostrar_codigos_reserva(request)
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


def _mostrar_codigos_reserva(request):
    """Gera os códigos de reserva e mostra a lista, uma única vez.

    A resposta não é redirecionada nem guardada: os códigos só existem nesta
    página, e o never_cache das views que chamam impede que o navegador ou um
    proxy guardem uma cópia dela.
    """
    return render(
        request,
        "accounts/codigos_reserva.html",
        {"codigos": codigos_reserva.gerar_codigos(request.user)},
    )


@login_required
@never_cache
def codigos_reserva_novos(request):
    """Troca os códigos de reserva por novos (os antigos deixam de valer)."""
    if request.method != "POST":
        return redirect("accounts:profile")

    # Os códigos abrem a conta sem o celular, então gerá-los exige o mesmo que
    # entrar nela: 2FA ativo e uma sessão que passou pelo segundo fator.
    tem_2fa = EncryptedTOTPDevice.objects.filter(user=request.user, confirmed=True).exists()
    if not (tem_2fa and request.user.is_verified()):
        messages.error(request, "Ative a verificação em duas etapas para gerar códigos de reserva.")
        return redirect("accounts:profile")

    return _mostrar_codigos_reserva(request)


@login_required
@never_cache
def otp_disable(request):
    """Desliga o 2FA só com a senha e um código válidos (risco R12)."""
    if not EncryptedTOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
        return redirect("accounts:profile")

    if request.user.is_staff:
        # Conta da equipe sem 2FA não entra (R05): desligar aqui trancaria a
        # pessoa do lado de fora no próximo login.
        messages.error(request, "Contas da equipe não podem desativar a verificação em duas etapas.")
        return redirect("accounts:profile")

    if confirmacao_bloqueada(request, "desativar_2fa"):
        return render(request, "accounts/limite_excedido.html", status=429)

    form = DesativarDoisFatoresForm(request.user, request.POST or None)

    if request.method == "POST":
        if not form.is_valid():
            registrar_confirmacao_errada(request, "desativar_2fa")
            registrar_evento(
                request, AuthEvent.Event.OTP_FALHOU, user=request.user,
                detail="confirmacao para desativar o 2FA",
            )
            return render(request, "accounts/otp_disable.html", {"form": form})

        EncryptedTOTPDevice.objects.filter(user=request.user).delete()
        codigos_reserva.apagar_codigos(request.user)
        request.user.two_factor_enabled = False
        request.user.save(update_fields=["two_factor_enabled"])

        # Desligar o segundo fator enfraquece a conta, então o evento fica
        # registrado: se a conta for invadida depois, a trilha mostra se a
        # proteção foi desligada antes e por qual endereço.
        registrar_evento(request, AuthEvent.Event.OTP_DESATIVADO, user=request.user)

        messages.warning(request, "Verificação em duas etapas desativada.")
        return redirect("accounts:profile")

    return render(request, "accounts/otp_disable.html", {"form": form})


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
            "codigos_restantes": codigos_reserva.restantes(request.user),
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


@limitar("recuperacao")
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


SESSAO_TOKEN_DE_RECUPERACAO = "recuperacao_token_id"


def password_reset_confirm(request, token):
    """Etapa 2a: o link do e-mail é conferido e o token sai da URL (R13).

    Com o token no endereço, ele ficava no histórico do navegador e seguia no
    cabeçalho Referer de qualquer recurso pedido pela página do formulário.
    Agora esta rota só confere o link, guarda na sessão o identificador do
    registro (não o token) e redireciona para um endereço sem ele.
    """
    registro, situacao = PasswordResetToken.resolver(token)
    resposta_de_falha = _recusar_token(request, registro, situacao)
    if resposta_de_falha is not None:
        return resposta_de_falha

    request.session[SESSAO_TOKEN_DE_RECUPERACAO] = registro.pk
    return redirect("accounts:password_reset_new")


@never_cache
def password_reset_new(request):
    """Etapa 2b: a senha nova é definida, num endereço sem o token."""
    registro = PasswordResetToken.objects.select_related("user").filter(
        pk=request.session.get(SESSAO_TOKEN_DE_RECUPERACAO)
    ).first()
    situacao = registro.situacao() if registro else PasswordResetToken.SITUACAO_INEXISTENTE
    resposta_de_falha = _recusar_token(request, registro, situacao)
    if resposta_de_falha is not None:
        request.session.pop(SESSAO_TOKEN_DE_RECUPERACAO, None)
        return resposta_de_falha

    return _definir_senha_nova(request, registro)


def _recusar_token(request, registro, situacao):
    """Resposta para token recusado, ou None se ele vale."""
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
    return None


def _definir_senha_nova(request, registro):
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
        request.session.pop(SESSAO_TOKEN_DE_RECUPERACAO, None)
        return redirect("accounts:password_reset_done")

    return render(request, "accounts/password_reset_confirm.html", {"form": form})
