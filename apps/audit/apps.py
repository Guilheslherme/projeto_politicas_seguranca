from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit'
    verbose_name = 'auditoria'

    def ready(self):
        # Importar o módulo é o que registra os receptores de sinal. Sem esta
        # linha o arquivo nunca seria carregado e nenhum login entraria na
        # trilha. O import fica aqui dentro, e não no topo do arquivo, porque
        # o ready() é chamado depois que os modelos já existem.
        from . import signals  # noqa: F401
