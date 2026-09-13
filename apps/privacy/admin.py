"""Consulta dos registros de consentimento no painel administrativo (requisitos 4.4 a 4.7)."""

from django.contrib import admin

from .models import ConsentRecord


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    """Registros de consentimento, apenas para leitura.

    O registro é a prova de que o consentimento foi obtido. Se a equipe pudesse
    criar ou editar aceites pelo painel, o registro deixaria de provar a vontade
    do titular, então os botões de criar, salvar e excluir são removidos.
    """

    list_display = ("granted_at", "user", "purpose", "policy_version", "revoked_at")
    list_filter = ("purpose", "policy_version", "granted_at")
    date_hierarchy = "granted_at"
    readonly_fields = [campo.name for campo in ConsentRecord._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
