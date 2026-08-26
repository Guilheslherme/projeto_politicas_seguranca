from django.shortcuts import render

# Create your views here.
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


def login_view(request):
    """Etapa 1 de 2: valida e-mail/senha. TODO: só criar sessão de fato após o OTP."""
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect('home')
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile_view(request):
    context = {
        'hash_algorithm': 'argon2',   # TODO: obter dinamicamente
        'session_expiry': request.session.get_expiry_date(),
        'has_2fa': False,             # TODO: checar se o usuário configurou OTP
        'is_verified': False,         # TODO: checar se a sessão passou pelo 2FA
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def otp_setup_view(request):
    context = {'qr_data_uri': '', 'secret_url': ''}  # TODO: gerar segredo TOTP real
    return render(request, 'accounts/otp_setup.html', context)


@login_required
def otp_verify_view(request):
    return render(request, 'accounts/otp_verify.html', {'email': request.user.email})


@login_required
def otp_disable_view(request):
    return redirect('accounts:profile')  # TODO: desativar o OTP de verdade