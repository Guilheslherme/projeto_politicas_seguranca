"""Leitura da trilha de autenticação em uma janela de tempo (requisito 5.4).

Uso:

    python manage.py analisar_logs            # últimas 24 horas
    python manage.py analisar_logs --horas 6

Também só lê o banco. Todas as contagens são feitas pelo banco, com values,
annotate e Count, em vez de trazer os registros e contar em Python: uma trilha
de auditoria só cresce, e um laço que funciona com mil linhas trava com um
milhão.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from apps.audit.models import AuthEvent

# Acima de 0,30 falha por login concluído o comando chama atenção.
#
# Este número é escolha nossa, não padrão de mercado: partimos de um uso normal,
# em que errar a senha uma vez a cada três ou quatro entradas já é bastante, e
# arredondamos. Serve para separar o dia comum de um dia estranho neste sistema,
# e teria que ser recalibrado com o tempo, olhando os números reais de uso.
LIMITE_DE_ALERTA = 0.30

# Quantas linhas mostrar nas listas de "quem mais aparece".
TOPO = 5


class Command(BaseCommand):
    help = "Resume a trilha de autenticacao das ultimas horas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--horas",
            type=int,
            default=24,
            help="Tamanho da janela analisada, em horas (padrao: 24).",
        )

    def handle(self, *args, **options):
        horas = options["horas"]
        inicio = timezone.now() - timedelta(hours=horas)
        eventos = AuthEvent.objects.filter(created_at__gte=inicio)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Trilha de autenticacao: ultimas {horas}h"))
        self.stdout.write(f"a partir de {inicio:%d/%m/%Y %H:%M}")
        self.stdout.write("")

        total = eventos.count()
        if total == 0:
            self.stdout.write("Nenhum evento registrado nesta janela.")
            return

        self._por_tipo(eventos)
        self._enderecos_com_mais_falhas(eventos)
        self._contas_mais_visadas(eventos)
        self._bloqueios(eventos)
        self._proporcao(eventos)

    def _por_tipo(self, eventos):
        """(a) O que aconteceu, do mais frequente para o menos frequente."""
        self.stdout.write(self.style.MIGRATE_LABEL("Eventos por tipo"))

        rotulos = dict(AuthEvent.Event.choices)
        linhas = eventos.values("event").annotate(total=Count("id")).order_by("-total")

        for linha in linhas:
            nome = rotulos.get(linha["event"], linha["event"])
            self.stdout.write(f"  {linha['total']:>5}  {nome}")
        self.stdout.write("")

    def _enderecos_com_mais_falhas(self, eventos):
        """(b) De onde vêm as senhas erradas."""
        self.stdout.write(self.style.MIGRATE_LABEL(f"Top {TOPO} enderecos com mais senha invalida"))

        linhas = (
            eventos.filter(event=AuthEvent.Event.LOGIN_FALHOU)
            .exclude(ip_address__isnull=True)
            .values("ip_address")
            .annotate(total=Count("id"))
            .order_by("-total")[:TOPO]
        )

        if not linhas:
            self.stdout.write("  nenhuma falha de senha nesta janela")
        for linha in linhas:
            self.stdout.write(f"  {linha['total']:>5}  {linha['ip_address']}")
        self.stdout.write("")

    def _contas_mais_visadas(self, eventos):
        """(c) Em quais contas insistiram, e quanto bateram em porta que não existe.

        O agrupamento é por usuario_ref, e não pelo vínculo com a conta, por um
        motivo prático: o vínculo vira nulo quando a conta é excluída. Se a
        contagem fosse por ele, os eventos de contas excluídas cairiam no mesmo
        balde das tentativas em endereços que nunca existiram, porque os dois
        têm vínculo nulo. O usuario_ref sobrevive à exclusão e mantém a
        separação.

        E as duas coisas são separadas na saída de propósito, porque contam
        histórias diferentes: insistir numa conta conhecida é ataque de senha;
        espalhar tentativas por endereços inexistentes é reconhecimento, alguém
        descobrindo quem tem cadastro aqui. Somadas num número só, o padrão
        desaparece.
        """
        falhas = eventos.filter(event=AuthEvent.Event.LOGIN_FALHOU)

        self.stdout.write(self.style.MIGRATE_LABEL(f"Top {TOPO} contas mais visadas"))
        linhas = (
            falhas.exclude(usuario_ref__isnull=True)
            .values("usuario_ref")
            .annotate(total=Count("id"))
            .order_by("-total")[:TOPO]
        )
        if not linhas:
            self.stdout.write("  nenhuma tentativa em conta existente")
        for linha in linhas:
            self.stdout.write(f"  {linha['total']:>5}  conta {linha['usuario_ref']}")
        self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_LABEL("Tentativas em enderecos sem conta no sistema"))
        sem_conta = falhas.filter(usuario_ref__isnull=True)
        quantas = sem_conta.count()
        de_quantos_ips = sem_conta.exclude(ip_address__isnull=True).values("ip_address").distinct().count()
        self.stdout.write(f"  {quantas:>5}  tentativas, vindas de {de_quantos_ips} endereco(s)")
        self.stdout.write("")

    def _bloqueios(self, eventos):
        """(d) Quantas contas o django-axes travou na janela."""
        self.stdout.write(self.style.MIGRATE_LABEL("Bloqueios por tentativas"))

        bloqueios = eventos.filter(event=AuthEvent.Event.CONTA_BLOQUEADA)
        quantos = bloqueios.count()

        # Contas distintas, porque a mesma conta pode ser bloqueada mais de uma
        # vez na mesma janela: o bloqueio expira em minutos e quem estava
        # tentando volta a tentar.
        contas = bloqueios.exclude(usuario_ref__isnull=True).values("usuario_ref").distinct().count()

        self.stdout.write(f"  {quantos:>5}  bloqueios, atingindo {contas} conta(s) identificada(s)")
        self.stdout.write("")

    def _proporcao(self, eventos):
        """(e) Falha por sucesso, comparando duas coisas da mesma natureza.

        As duas pontas são tentativas de entrar: senha recusada de um lado,
        sessão criada do outro. Dividir falhas pelo total de eventos daria um
        número menor e sem significado, porque o total inclui logout, cadastro
        e segundo fator, que não são tentativas de entrar.
        """
        self.stdout.write(self.style.MIGRATE_LABEL("Proporcao entre falha e sucesso"))

        falhas = eventos.filter(event=AuthEvent.Event.LOGIN_FALHOU).count()
        sucessos = eventos.filter(event=AuthEvent.Event.LOGIN_OK).count()

        self.stdout.write(f"  {falhas} senha(s) invalida(s) para {sucessos} login(s) concluido(s)")

        if sucessos == 0:
            if falhas:
                self.stdout.write(
                    self.style.WARNING(
                        "  ALERTA: houve tentativa de entrada e nenhuma deu certo nesta janela."
                    )
                )
            else:
                self.stdout.write("  sem tentativas de entrada nesta janela")
            self.stdout.write("")
            return

        proporcao = falhas / sucessos
        self.stdout.write(f"  {proporcao:.2f} falha por login concluido")

        if proporcao > LIMITE_DE_ALERTA:
            self.stdout.write(
                self.style.WARNING(
                    f"  ALERTA: acima do limite de {LIMITE_DE_ALERTA:.2f} que adotamos."
                )
            )
        self.stdout.write("")
