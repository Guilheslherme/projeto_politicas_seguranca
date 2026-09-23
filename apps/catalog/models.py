"""Acervo do portal: sintomas, condições e os materiais que ligam os dois.

Quem liga um sintoma a uma condição é a FONTE, nunca o nosso código. E nenhum
modelo aqui tem campo de peso, pontuação ou probabilidade: com um campo desses
o portal ordenaria por chance e viraria um verificador de sintomas.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Sintoma(models.Model):
    """Um sintoma que a pessoa pode marcar na tela do filtro."""

    nome = models.CharField("nome", max_length=60)
    slug = models.SlugField("apelido na URL", unique=True)

    """ Marca os sinais que não podem esperar. Quando um deles é marcado, a tela
    de resultado não monta lista nenhuma: mostra o aviso para procurar
    atendimento e para por ali. """
    alerta = models.BooleanField("sinal de alerta", default=False)

    class Meta:
        verbose_name = "sintoma"
        verbose_name_plural = "sintomas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Condicao(models.Model):
    """Uma condição de saúde, escrita como a fonte a nomeia."""

    nome = models.CharField("nome", max_length=120)
    slug = models.SlugField("apelido na URL", unique=True)
    resumo = models.TextField("resumo")

    # Em que situação aquela condição pede atendimento. Fica no modelo, e não no
    # template, porque muda de condição para condição e sai da fonte.
    quando_procurar = models.TextField("quando procurar atendimento")

    class Meta:
        verbose_name = "condicao"
        verbose_name_plural = "condicoes"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Material(models.Model):
    """Um texto publicado por um órgão de saúde.

    O portal guarda título, resumo e link, nunca o conteúdo inteiro da fonte.
    Isso é decisão, e não esquecimento: evita problema de direito autoral e
    mantém a fonte como dona do que escreveu.
    """

    titulo = models.CharField("titulo", max_length=200)
    resumo = models.TextField("resumo")
    fonte = models.CharField("fonte", max_length=120)
    url_original = models.URLField("endereco original")
    """ Opcional porque muitas páginas de órgãos de saúde não mostram data de
    publicação. Ficar em branco é a resposta honesta nesse caso: inventar uma
    data seria forjar a procedência do material, que é justamente o que este
    modelo existe para garantir. """
    publicado_em = models.DateField("publicado em", null=True, blank=True)

    """ Quando a fonte retira ou revisa um material, ele sai do site sem sair do
    banco: basta desmarcar aqui. A condição que perde todos os materiais ativos
    deixa de aparecer nos resultados, porque não sobra quem afirme a ligação. """
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "material"
        verbose_name_plural = "materiais"
        ordering = ["-publicado_em"]

    def __str__(self):
        return f"{self.titulo} ({self.fonte})"


class Associacao(models.Model):
    """A ligação entre um sintoma e uma condição, afirmada por um material."""

    sintoma = models.ForeignKey(
        Sintoma, on_delete=models.CASCADE, related_name="associacoes", verbose_name="sintoma"
    )
    condicao = models.ForeignKey(
        Condicao, on_delete=models.CASCADE, related_name="associacoes", verbose_name="condicao"
    )

    """ Obrigatório, sem null e sem blank: é a regra do projeto virando banco de
    dados. Sem fonte, não existe associação. O CASCADE segue a mesma ideia — se
    o material for apagado, some junto a ligação que só ele sustentava. """
    material = models.ForeignKey(
        Material, on_delete=models.CASCADE, related_name="associacoes", verbose_name="material"
    )

    class Meta:
        verbose_name = "associacao"
        verbose_name_plural = "associacoes"
        # O mesmo material não afirma a mesma ligação duas vezes.
        unique_together = ("sintoma", "condicao", "material")

    def __str__(self):
        return f"{self.sintoma} -> {self.condicao} (por {self.material.fonte})"


class MaterialSalvo(models.Model):
    """Um material que a pessoa guardou na conta.

    Esta é a única parte do sistema que toca dado sensível. Guardar um material
    sobre asma indica interesse por um tema de saúde, e a LGPD trata isso como
    dado pessoal sensível (Art. 5º, II).

    Por isso a função não vem ligada: ela depende de um consentimento próprio,
    para esta finalidade e só para ela, pedido em tela separada. Consentimento
    genérico não vale para finalidade determinada (Art. 8º, §4º), então o aceite
    da Política de Privacidade feito no cadastro não autoriza isto aqui.

    O que fica guardado é o mínimo: qual material e quando. Não há anotação,
    nem nota, nem motivo — nada que a pessoa escreva sobre a própria saúde.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="materiais_salvos",
        verbose_name="usuario",
    )
    material = models.ForeignKey(
        Material, on_delete=models.CASCADE, related_name="salvos", verbose_name="material"
    )
    salvo_em = models.DateTimeField("salvo em", default=timezone.now)

    class Meta:
        verbose_name = "material salvo"
        verbose_name_plural = "materiais salvos"
        ordering = ["-salvo_em"]
        # CASCADE nos dois lados: excluída a conta, ou apagado o material, o
        # registro vai junto. Ele não tem valor de auditoria — é preferência da
        # pessoa, e preferência sem dono não serve para nada.
        unique_together = ("user", "material")

    def __str__(self):
        return f"{self.material.titulo} (usuario={self.user_id})"
