"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
#conecta as urls a view que contem a pagina home, quando o usuario acessar tal url mostra tal pagina
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("conta/", include("apps.accounts.urls")),
    path("privacidade/", include("apps.privacy.urls")),

    # O acervo entra na raiz, para os endereços ficarem /sintomas/ e
    # /condicoes/<slug>/. Vem depois da home porque o padrão "" acima casa
    # apenas com o endereço vazio, e não engole os de baixo.
    path("", include("apps.catalog.urls")),
]
    