"""Consulta da trilha de auditoria no painel administrativo (requisitos 2.6 e 2.7)."""

from django.contrib import admin

from .models import PasswordResetLog


@admin.register(PasswordResetLog)
class PasswordResetLogAdmin(admin.ModelAdmin):
    """Log de recuperação de senha, apenas para leitura.

    O painel serve para consultar e analisar os eventos, nunca para editá-los:
    uma trilha de auditoria que a própria equipe pode alterar não comprova nada.
    Os três métodos abaixo removem os botões de criar, salvar e excluir para
    todo mundo, inclusive para o superusuário.
    """

    # A coluna do usuário mostra o identificador interno. Não há busca por
    # e-mail porque o endereço não é gravado aqui: para chegar aos eventos de
    # uma conta, parte-se do usuário e não do endereço.
    list_display = ("created_at", "event", "user", "ip_address")
    list_filter = ("event", "created_at")
    search_fields = ("ip_address",)
    date_hierarchy = "created_at"

    # Monta a lista a partir dos próprios campos do modelo, assim um campo novo
    # já nasce protegido, sem depender de alguém lembrar de acrescentá-lo aqui.
    readonly_fields = [campo.name for campo in PasswordResetLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
