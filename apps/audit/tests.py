"""Testes da trilha de autenticação (requisitos 5.1, 5.2 e 5.3)."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from .models import AuthEvent

User = get_user_model()

SENHA = "TrocaEssaSenha2026"


def criar_conta(email="pessoa@exemplo.com"):
    return User.objects.create_user(
        email=email,
        full_name="Pessoa de Teste",
        password=SENHA,
    )


class RegistroDeEventosTests(TestCase):
    """Requisitos 5.1 e 5.2: o que entra na trilha, e o que não pode entrar."""

    def test_login_bem_sucedido_grava_o_evento(self):
        user = criar_conta()

        self.client.post(
            reverse("accounts:login"),
            {"username": user.email, "password": SENHA},
        )

        evento = AuthEvent.objects.get(event=AuthEvent.Event.LOGIN_OK)
        self.assertEqual(evento.usuario_ref, user.pk)
        self.assertEqual(evento.user_id, user.pk)

    def test_senha_errada_em_conta_existente_identifica_a_conta(self):
        user = criar_conta()

        self.client.post(
            reverse("accounts:login"),
            {"username": user.email, "password": "senha-que-nao-e-a-dela"},
        )

        evento = AuthEvent.objects.get(event=AuthEvent.Event.LOGIN_FALHOU)
        self.assertEqual(evento.usuario_ref, user.pk)

        # O e-mail digitado serve para achar a conta e nada mais. Este laço
        # varre todos os campos de texto do registro: se algum dia alguém
        # resolver "melhorar" o log guardando o endereço, o teste quebra.
        for campo in AuthEvent._meta.fields:
            valor = getattr(evento, campo.attname)
            if isinstance(valor, str):
                self.assertNotIn(user.email, valor)

    def test_senha_errada_em_endereco_sem_conta_fica_sem_vinculo(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": "nao-existe@exemplo.com", "password": "qualquer-coisa"},
        )

        evento = AuthEvent.objects.get(event=AuthEvent.Event.LOGIN_FALHOU)
        self.assertIsNone(evento.user_id)
        self.assertIsNone(evento.usuario_ref)


class CadeiaDeHashesTests(TestCase):
    """Requisito 5.3: o encadeamento e a conferência."""

    def gravar_tres_eventos(self):
        return [
            AuthEvent.registrar(None, AuthEvent.Event.LOGIN_OK, detail=f"evento {n}")
            for n in (1, 2, 3)
        ]

    def test_primeiro_registro_aponta_para_a_genese(self):
        AuthEvent.registrar(None, AuthEvent.Event.LOGIN_OK)

        primeiro = AuthEvent.objects.order_by("id").first()
        self.assertEqual(primeiro.hash_anterior, AuthEvent.GENESE)

    def test_cada_registro_aponta_para_o_anterior(self):
        self.gravar_tres_eventos()

        registros = list(AuthEvent.objects.order_by("id"))
        anterior = AuthEvent.GENESE
        for registro in registros:
            self.assertEqual(registro.hash_anterior, anterior)
            self.assertEqual(registro.hash_atual, registro.calcular_hash())
            anterior = registro.hash_atual

    def test_alterar_um_registro_do_meio_e_denunciado(self):
        registros = self.gravar_tres_eventos()
        do_meio = registros[1]

        # Alteração direta no banco, sem passar pelo modelo: é assim que um
        # ataque à trilha aconteceria de verdade, com acesso ao banco e não
        # pela aplicação.
        AuthEvent.objects.filter(pk=do_meio.pk).update(detail="alterado na marra")

        erro = StringIO()
        with self.assertRaises(CommandError):
            call_command("verificar_logs", stdout=StringIO(), stderr=erro)

        # Não basta falhar: a saída tem que dizer qual registro e qual das duas
        # conferências não bateu, senão não serve para investigar nada.
        diagnostico = erro.getvalue()
        self.assertIn(f"id={do_meio.pk}", diagnostico)
        self.assertIn("conteudo alterado", diagnostico)

    def test_cadeia_intacta_passa_na_verificacao(self):
        self.gravar_tres_eventos()

        saida = StringIO()
        call_command("verificar_logs", stdout=saida, stderr=StringIO())

        self.assertIn("Cadeia integra", saida.getvalue())
        self.assertIn("3 registros", saida.getvalue())


class AnaliseDaTrilhaTests(TestCase):
    """Requisito 5.4: o comando que resume a trilha."""

    def test_resumo_separa_conta_conhecida_de_endereco_sem_conta(self):
        user = criar_conta()

        AuthEvent.registrar(None, AuthEvent.Event.LOGIN_OK, user=user)
        for _ in range(3):
            AuthEvent.registrar(None, AuthEvent.Event.LOGIN_FALHOU, user=user)
        # Falha em endereço que não tem conta: entra sem vínculo e sem número.
        AuthEvent.registrar(None, AuthEvent.Event.LOGIN_FALHOU)

        saida = StringIO()
        call_command("analisar_logs", "--horas", "1", stdout=saida)
        texto = saida.getvalue()

        # As três falhas da conta conhecida e a do endereço sem conta não podem
        # cair no mesmo balde: são padrões de ataque diferentes.
        self.assertIn(f"conta {user.pk}", texto)
        self.assertIn("Tentativas em enderecos sem conta", texto)

        # 4 falhas para 1 login concluído, bem acima do limite que adotamos.
        self.assertIn("4.00 falha por login concluido", texto)
        self.assertIn("ALERTA", texto)


class ExclusaoDeContaTests(TestCase):
    """A exclusão da conta não pode furar a trilha nem quebrar a cadeia.

    Esta classe existe por causa de um defeito real: quando a conta era apagada
    antes do logout, o evento de fim de sessão se perdia em silêncio. Os testes
    passavam, e o traço do erro só aparecia para quem fosse ler a saída do
    servidor.
    """

    def entrar_e_excluir(self):
        user = criar_conta()
        self.client.post(
            reverse("accounts:login"),
            {"username": user.email, "password": SENHA},
        )
        self.client.post(reverse("privacy:delete_account"), {"password": SENHA})
        return user

    def test_exclusao_grava_os_dois_eventos_com_o_identificador(self):
        user = self.entrar_e_excluir()

        self.assertFalse(User.objects.filter(pk=user.pk).exists())

        excluida = AuthEvent.objects.get(event=AuthEvent.Event.CONTA_EXCLUIDA)
        saida = AuthEvent.objects.get(event=AuthEvent.Event.LOGOUT)

        # O vínculo com a conta some junto com ela, mas o identificador selado
        # fica: é ele que mantém os dois eventos ligados à mesma pessoa.
        self.assertIsNone(excluida.user_id)
        self.assertIsNone(saida.user_id)
        self.assertEqual(excluida.usuario_ref, user.pk)
        self.assertEqual(saida.usuario_ref, user.pk)

        # E a cadeia continua fechando depois da exclusão, que é o ponto de
        # gravar o número em vez do vínculo.
        call_command("verificar_logs", stdout=StringIO(), stderr=StringIO())

    def test_o_fluxo_nao_deixa_erro_na_saida_do_servidor(self):
        # A gravação da trilha engole exceções para não derrubar a tela, então
        # uma falha aqui não apareceria como teste vermelho: apareceria como
        # uma linha de ERROR no log e um evento faltando. Este teste vigia
        # exatamente isso.
        with self.assertNoLogs("apps", level="ERROR"):
            self.entrar_e_excluir()
