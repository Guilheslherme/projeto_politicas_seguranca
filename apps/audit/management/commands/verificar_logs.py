"""Conferência da cadeia de hashes da trilha de autenticação (requisito 5.3).

Uso:

    python manage.py verificar_logs

O comando só lê o banco. Ele não altera, não apaga e não regrava nada: se
existisse aqui uma rotina capaz de recalcular a cadeia, ela seria a ferramenta
pronta para o ataque que este mesmo comando deveria denunciar.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.audit.models import AuthEvent


class Command(BaseCommand):
    help = "Confere se a trilha de autenticacao foi alterada depois de gravada."

    def handle(self, *args, **options):
        # Ordem crescente de id, que é a ordem em que os registros entraram e
        # portanto a ordem em que a cadeia foi montada. Ordenar por data daria
        # quase sempre o mesmo resultado, mas "quase sempre" não serve aqui:
        # dois eventos no mesmo instante ficariam em ordem indefinida.
        consulta = AuthEvent.objects.order_by("id").iterator()

        # O hash que o próximo registro tem que declarar como anterior. O
        # primeiro de todos precisa apontar para a gênese.
        esperado = AuthEvent.GENESE
        total = 0
        problema = None

        for registro in consulta:
            total += 1

            # Primeira conferência: o elo. Este registro aponta mesmo para o
            # anterior? Se um registro do meio foi apagado, é aqui que aparece.
            if registro.hash_anterior != esperado:
                problema = (registro, "elo quebrado", esperado, registro.hash_anterior)
                break

            # Segunda conferência: o conteúdo. Recalcula o hash a partir dos
            # campos gravados e compara com o que está guardado. Se alguém
            # editou o evento, a data ou o IP direto no banco, o resumo
            # recalculado sai diferente do que está na linha.
            recalculado = registro.calcular_hash()
            if recalculado != registro.hash_atual:
                problema = (registro, "conteudo alterado", registro.hash_atual, recalculado)
                break

            esperado = registro.hash_atual

        # Fecha o cursor antes de escrever qualquer coisa. Sair do laço por
        # break deixa a leitura do banco pendente, e denunciar o erro com a
        # consulta ainda aberta faz o SQLite reclamar de interrupção no meio da
        # leitura, escondendo o defeito de verdade atrás de um erro de banco.
        consulta.close()

        if problema is None:
            self.stdout.write(
                self.style.SUCCESS(f"Cadeia integra: {total} registros verificados.")
            )
            return

        registro, motivo, esperado, encontrado = problema

        # O diagnóstico vai para a saída de erro, o mesmo caminho do
        # CommandError logo abaixo. Escrever o diagnóstico na saída normal e o
        # erro na de erro faria as duas mensagens aparecerem fora de ordem no
        # terminal, porque são fluxos diferentes com ritmos diferentes.
        self.stderr.write(self.style.ERROR("Cadeia quebrada."))
        self.stderr.write(f"  registro id={registro.id}")
        self.stderr.write(f"  data:    {registro.created_at:%d/%m/%Y %H:%M:%S}")
        self.stderr.write(f"  evento:  {registro.event}")

        if motivo == "elo quebrado":
            self.stderr.write("  falha:   elo quebrado (o registro anterior sumiu ou mudou)")
            self.stderr.write(f"  esperava hash anterior: {esperado}")
            self.stderr.write(f"  encontrou:              {encontrado}")
        else:
            self.stderr.write("  falha:   conteudo alterado depois de gravado")
            self.stderr.write(f"  hash gravado:    {esperado}")
            self.stderr.write(f"  hash recalculado:{encontrado}")

        self.stderr.write(f"  registros conferidos antes da falha: {total - 1}")

        raise CommandError(
            f"A trilha de autenticacao foi alterada a partir do registro {registro.id}."
        )
