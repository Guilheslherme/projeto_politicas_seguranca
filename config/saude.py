"""Rota de saúde para o monitor de disponibilidade (risco R04)."""

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def saude(request):
    """Diz só se o site e o banco estão respondendo.

    Não traz versão, nome do servidor, contagem de registros nem a mensagem do
    erro: um monitor só precisa saber se está no ar, e qualquer detalhe a mais
    ajudaria quem está mapeando o sistema.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "indisponivel"}, status=503)
    return JsonResponse({"status": "ok"})
