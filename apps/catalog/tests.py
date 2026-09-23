"""Testes do acervo e do consentimento por finalidade.

Os nomes do conteúdo de teste são claramente falsos ("Condição de teste A")
para ninguém confundir dado de teste com material real cadastrado das fontes.

Os testes também criam o próprio sintoma, em vez de usar um dos dez do escopo.
O motivo é isolamento: a migração 0005 carrega o acervo real no banco de teste,
e usar "Febre" faria estes testes enxergarem as condições de verdade junto com
as inventadas aqui.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.privacy.models import ConsentRecord

from .models import Associacao, Condicao, Material, MaterialSalvo, Sintoma

User = get_user_model()

SENHA = "TrocaEssaSenha2026"
BACKEND = "django.contrib.auth.backends.ModelBackend"


def criar_material(titulo="Material de teste", ativo=True):
    return Material.objects.create(
        titulo=titulo,
        resumo="Resumo do material de teste.",
        fonte="Fonte de teste",
        url_original=f"https://exemplo.invalido/{titulo.replace(' ', '-').lower()}",
        ativo=ativo,
    )


def criar_condicao(nome, slug):
    return Condicao.objects.create(
        nome=nome, slug=slug, resumo="Resumo de teste.", quando_procurar="Texto de teste."
    )


class AcervoTests(TestCase):
    """O que a tela de resultado mostra, e com base em quê."""

    def setUp(self):
        self.sintoma = Sintoma.objects.create(
            nome="Sintoma de teste", slug="sintoma-de-teste", alerta=False
        )

    def buscar(self, *slugs):
        return self.client.get(reverse("catalog:resultado"), {"s": list(slugs)})

    def test_tela_de_sintomas_responde(self):
        """1. A tela de marcar sintomas abre."""
        self.assertEqual(self.client.get(reverse("catalog:sintomas")).status_code, 200)

    def test_sinal_de_alerta_interrompe_e_nao_lista_condicao(self):
        """2. O desvio de alerta: nenhuma condição pode vazar para a tela.

        Este é o teste que prova a decisão de segurança do projeto. Marcar um
        sinal de alerta junto com um sintoma comum que TEM condição cadastrada
        ainda assim não pode mostrar lista nenhuma.
        """
        condicao = criar_condicao("Condicao de teste A", "cond-a")
        Associacao.objects.create(
            sintoma=self.sintoma, condicao=condicao, material=criar_material()
        )

        resposta = self.buscar("sintoma-de-teste", "dor-no-peito")

        self.assertContains(resposta, "Procure atendimento agora")
        self.assertNotContains(resposta, "Condicao de teste A")
        # A tela de alerta também não mostra menu: qualquer link para outra
        # parte do site é convite para adiar o atendimento.
        self.assertNotContains(resposta, 'class="menu"')

    def test_condicao_so_aparece_com_associacao(self):
        """3. Sem associação, a condição não existe para a busca."""
        criar_condicao("Condicao de teste A", "cond-a")

        resposta = self.buscar("sintoma-de-teste")

        self.assertNotContains(resposta, "Condicao de teste A")
        self.assertContains(resposta, "ainda")

    def test_material_desativado_tira_a_condicao(self):
        """4. Material fora do ar derruba a condição que só ele sustentava."""
        condicao = criar_condicao("Condicao de teste A", "cond-a")
        material = criar_material()
        Associacao.objects.create(sintoma=self.sintoma, condicao=condicao, material=material)

        self.assertContains(self.buscar("sintoma-de-teste"), "Condicao de teste A")

        material.ativo = False
        material.save(update_fields=["ativo"])

        self.assertNotContains(self.buscar("sintoma-de-teste"), "Condicao de teste A")

    def test_lista_sai_em_ordem_alfabetica(self):
        """5. A ordem é alfabética, nunca por probabilidade ou relevância."""
        material = criar_material()
        for nome, slug in [
            ("Condicao de teste C", "cond-c"),
            ("Condicao de teste A", "cond-a"),
            ("Condicao de teste B", "cond-b"),
        ]:
            Associacao.objects.create(
                sintoma=self.sintoma, condicao=criar_condicao(nome, slug), material=material
            )

        corpo = self.buscar("sintoma-de-teste").content.decode()
        posicoes = [corpo.index(f"Condicao de teste {letra}") for letra in "ABC"]
        self.assertEqual(posicoes, sorted(posicoes))

    def test_condicao_por_dois_sintomas_aparece_uma_vez(self):
        """6. distinct(): a mesma condição não se repete na tela."""
        outro = Sintoma.objects.create(
            nome="Outro sintoma de teste", slug="outro-sintoma-de-teste", alerta=False
        )
        condicao = criar_condicao("Condicao de teste A", "cond-a")
        material = criar_material()
        Associacao.objects.create(sintoma=self.sintoma, condicao=condicao, material=material)
        Associacao.objects.create(sintoma=outro, condicao=condicao, material=material)

        corpo = self.buscar("sintoma-de-teste", "outro-sintoma-de-teste").content.decode()

        self.assertEqual(corpo.count("Condicao de teste A"), 1)


class ComentariosDeTemplateTests(TestCase):
    """Trava para um defeito que já apareceu três vezes neste projeto.

    O comentário curto do Django, {# ... #}, só funciona quando abre e fecha na
    mesma linha. Espalhado por duas, ele deixa de ser comentário: o texto vai
    para o HTML e aparece na tela do usuário. Pior, se houver uma tag dentro
    dele, ela é executada.

    Nada avisa quando isso acontece — a página continua respondendo 200. Este
    teste varre todos os templates do projeto e é o único aviso que existe.
    Para comentário de várias linhas, o certo é {% comment %} ... {% endcomment %}.
    """

    def test_comentario_curto_nao_atravessa_linhas(self):
        falhas = []
        for caminho in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
                if "{#" in linha and "#}" not in linha:
                    relativo = caminho.relative_to(settings.BASE_DIR)
                    falhas.append(f"{relativo}:{numero}")

        self.assertEqual(
            falhas,
            [],
            "Comentario {# #} aberto sem fechar na mesma linha. O texto vai "
            "aparecer na tela. Use {% comment %} ... {% endcomment %}. Em: "
            + ", ".join(falhas),
        )


class ConsentimentoPorFinalidadeTests(TestCase):
    """Guardar material depende de consentimento próprio (Art. 8º, §4º)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="pessoa@exemplo.com", full_name="Pessoa de Teste", password=SENHA
        )
        # O aceite da conta existe; o de guardar materiais, não. É exatamente
        # essa diferença que os dois testes abaixo cobram.
        ConsentRecord.registrar_aceite(self.user)
        self.client.force_login(self.user, backend=BACKEND)
        self.material = criar_material()

    def test_salvar_sem_consentimento_e_recusado(self):
        """7. Aceitar a política no cadastro não autoriza guardar material."""
        resposta = self.client.post(
            reverse("catalog:salvar_material", args=[self.material.id])
        )

        self.assertEqual(MaterialSalvo.objects.count(), 0)
        self.assertRedirects(
            resposta,
            f"{reverse('catalog:consentimento_materiais')}?material={self.material.id}",
        )

    def test_revogar_apaga_os_salvamentos_e_poupa_a_conta(self):
        """8. Revogar uma finalidade não derruba o consentimento da conta."""
        self.client.post(
            reverse("catalog:consentimento_materiais"), {"material": self.material.id}
        )
        self.assertEqual(MaterialSalvo.objects.count(), 1)

        self.client.post(reverse("catalog:revogar_materiais"))

        # Sem consentimento não há base legal para manter os dados, então eles
        # são eliminados junto (Arts. 15, III, e 16 da LGPD).
        self.assertEqual(MaterialSalvo.objects.count(), 0)
        self.assertFalse(
            ConsentRecord.tem_consentimento_vigente(
                self.user, ConsentRecord.Purpose.MATERIAL_SALVO
            )
        )
        # E a conta continua de pé: quem desiste de guardar materiais não está
        # desistindo da conta.
        self.assertTrue(ConsentRecord.tem_consentimento_vigente(self.user))
