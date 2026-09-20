"""Consulta das trilhas de auditoria no painel (requisitos 2.6, 2.7 e 5.1 a 5.3)."""

from django.contrib import admin

from .models import AuthEvent, PasswordResetLog


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


@admin.register(AuthEvent)
class AuthEventAdmin(admin.ModelAdmin):
    """Trilha de autenticação, apenas para leitura (requisito 5.3).

    Mesmo padrão do painel acima, pelo mesmo motivo: o painel serve para
    consultar, nunca para editar. Aqui isso pesa ainda mais, porque cada
    registro carrega o hash do anterior — uma edição pelo painel não só
    apagaria a verdade do evento, como quebraria a conferência de todos os
    registros seguintes.
    """

    # O identificador selado tem coluna própria porque é o que sobra quando a
    # conta é excluída: o vínculo vira nulo, e sem este número os eventos de
    # contas já apagadas ficariam sem identificação nenhuma na tela.
    list_display = ("created_at", "event", "user", "usuario_ref", "ip_address")
    list_filter = ("event", "created_at")

    # Busca só por endereço de rede. O e-mail digitado nas tentativas não é
    # gravado em campo nenhum, então não há o que procurar por ele.
    search_fields = ("ip_address",)
    date_hierarchy = "created_at"

    readonly_fields = [campo.name for campo in AuthEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
