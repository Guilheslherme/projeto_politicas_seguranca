"""Cadastro do acervo pelo painel administrativo.

Não existe tela de cadastro de conteúdo no site: quem cadastra condição,
material e associação somos nós, por aqui, lendo a fonte antes.
"""

from django.contrib import admin

from .models import Associacao, Condicao, Material, Sintoma


@admin.register(Sintoma)
class SintomaAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "alerta")
    list_filter = ("alerta",)
    # Monta o apelido da URL enquanto o nome é digitado, para ninguém inventar
    # um slug com acento ou espaço.
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Condicao)
class CondicaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug")
    search_fields = ("nome",)
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    # A coluna "ativo" fica na lista, e não só no formulário, porque tirar um
    # material do ar é a ação mais comum aqui: é o que a gente faz quando a
    # fonte revisa ou retira o texto.
    list_display = ("titulo", "fonte", "publicado_em", "ativo")
    list_filter = ("fonte", "ativo")
    search_fields = ("titulo",)


@admin.register(Associacao)
class AssociacaoAdmin(admin.ModelAdmin):
    list_display = ("sintoma", "condicao", "material")
    list_filter = ("sintoma", "condicao")
