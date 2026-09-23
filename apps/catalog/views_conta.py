"""O que a conta oferece no acervo: guardar materiais.

Separado de views.py de propósito. Lá ficam as telas públicas, que não gravam
nada e não exigem login. Aqui ficam as que escrevem no banco — e são as únicas
do projeto que tocam dado sensível, porque guardar um material indica interesse
por um tema de saúde.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.privacy.models import ConsentRecord

from .models import Material, MaterialSalvo

# A finalidade é uma só, e fica numa constante para não haver duas grafias dela
# espalhadas pelo arquivo.
FINALIDADE = ConsentRecord.Purpose.MATERIAL_SALVO


@login_required
def consentimento(request):
    """Pede o consentimento específico de guardar materiais.

    Esta tela existe porque o aceite da Política de Privacidade, dado no
    cadastro, não serve aqui: a LGPD exige consentimento para finalidade
    determinada, e um aceite genérico é nulo (Art. 8º, §4º).
    """
    # Guarda para qual material a pessoa veio, para salvá-lo logo depois do
    # aceite em vez de obrigá-la a procurar a página de novo.
    material_id = request.GET.get("material") or request.POST.get("material")

    if request.method == "POST":
        ConsentRecord.registrar_aceite(request.user, FINALIDADE)
        messages.success(request, "Consentimento registrado. Agora você pode guardar materiais.")
        if material_id:
            return _guardar(request, material_id)
        return redirect("catalog:meus_materiais")

    return render(request, "catalog/consentimento_materiais.html", {"material_id": material_id})


@login_required
@require_POST
def salvar(request, material_id):
    """Guarda um material, se houver consentimento para isso."""
    if not ConsentRecord.tem_consentimento_vigente(request.user, FINALIDADE):
        # Sem o consentimento daquela finalidade, nada é gravado: a pessoa é
        # levada à tela que explica o que está sendo pedido.
        return redirect(f"{reverse('catalog:consentimento_materiais')}?material={material_id}")
    return _guardar(request, material_id)


def _guardar(request, material_id):
    """Grava o material e devolve a pessoa para a página da condição."""
    material = get_object_or_404(Material, pk=material_id, ativo=True)
    MaterialSalvo.objects.get_or_create(user=request.user, material=material)
    messages.success(request, "Material guardado na sua conta.")
    return redirect("catalog:meus_materiais")


@login_required
def meus_materiais(request):
    """Lista o que a pessoa guardou, com o que fazer a respeito."""
    return render(
        request,
        "catalog/meus_materiais.html",
        {
            "salvos": MaterialSalvo.objects.filter(user=request.user).select_related("material"),
            "consentiu": ConsentRecord.tem_consentimento_vigente(request.user, FINALIDADE),
        },
    )


@login_required
@require_POST
def remover(request, material_id):
    """Apaga um item da lista, sem mexer no consentimento."""
    MaterialSalvo.objects.filter(user=request.user, material_id=material_id).delete()
    messages.info(request, "Material removido da sua lista.")
    return redirect("catalog:meus_materiais")


@login_required
@require_POST
def revogar(request):
    """Revoga o consentimento desta finalidade e apaga o que foi guardado.

    As duas coisas andam juntas por obrigação: sem consentimento não existe base
    legal para manter os dados, e a LGPD manda eliminá-los ao fim do tratamento
    (Arts. 15, III, e 16). Revogar e deixar a lista de pé seria fingir que
    revogou.

    O consentimento da conta não é tocado: quem desiste de guardar materiais não
    está desistindo da conta.
    """
    MaterialSalvo.objects.filter(user=request.user).delete()
    ConsentRecord.revogar(request.user, FINALIDADE)
    messages.warning(request, "Consentimento revogado e materiais guardados apagados.")
    return redirect("catalog:meus_materiais")
