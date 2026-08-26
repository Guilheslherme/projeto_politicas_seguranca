from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('otp/setup/', views.otp_setup_view, name='otp_setup'),
    path('otp/verify/', views.otp_verify_view, name='otp_verify'),
    path('otp/disable/', views.otp_disable_view, name='otp_disable'),
]