"""Direitos do titular: consulta, exportação e exclusão (requisitos 4.8 a 4.10).

A consulta e a exportação usam a mesma função de coleta. Assim o que a pessoa
vê na tela é exatamente o que ela baixa, e nenhum dado aparece em um e não no
outro.
"""

from axes.models import AccessAttempt, AccessFailureLog, AccessLog
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import EncryptedTOTPDevice
from apps.audit.models import PasswordResetLog
from apps.catalog.models import MaterialSalvo

from .models import ConsentRecord


def reunir_dados_do_titular(user):
    """Junta tudo que o sistema guarda sobre a conta, organizado por categoria.

    Inclui as tabelas de bibliotecas de terceiros (django-axes), e não só as
    do projeto: o direito de acesso vale para todo dado tratado, não apenas para
    o que o projeto escreveu.
    """
    # O django-axes identifica as tentativas pelo que foi digitado no campo de
    # e-mail, que pode ter vindo com maiúsculas. Por isso a comparação ignora
    # a caixa das letras.
    acessos = AccessLog.objects.filter(username__iexact=user.email).order_by("-attempt_time")
    tentativas = AccessAttempt.objects.filter(username__iexact=user.email).order_by("-attempt_time")
    tem_2fa = EncryptedTOTPDevice.objects.filter(user=user, confirmed=True).exists()

    return {
        "gerado_em": timezone.now(),
        "conta": {
            "nome_completo": user.full_name,
            "email": user.email,
            "cadastrado_em": user.date_joined,
            "ultima_troca_de_senha": user.last_password_change,
            "verificacao_em_duas_etapas": "ativa" if tem_2fa else "inativa",
        },
        # A senha e o segredo do 2FA são informados como existentes, mas o valor
        # não sai. O hash da senha permitiria a quem obtivesse o arquivo tentar
        # descobrir a senha por força bruta fora do sistema, e o segredo do 2FA
        # permitiria gerar os códigos de acesso. Um arquivo baixado fica fora
        # das proteções do sistema, então não pode carregar credenciais.
        "credenciais": {
            "senha": "Guardada apenas como hash Argon2id, que não permite recuperar "
            "a senha. Não é exportada por segurança.",
            "segredo_do_2fa": (
                "Guardado cifrado com AES-256-GCM. Não é exportado por segurança."
                if tem_2fa
                else "Não existe: a verificação em duas etapas está inativa."
            ),
        },
        # A única categoria de dado sensível do sistema: guardar um material
        # indica interesse por um tema de saúde. Entra aqui separada das
        # outras, e não misturada na conta, para a pessoa enxergar de imediato
        # o que existe sobre ela nessa categoria.
        "materiais_guardados": [
            {
                "material": salvo.material.titulo,
                "fonte": salvo.material.fonte,
                "guardado_em": salvo.salvo_em,
            }
            for salvo in MaterialSalvo.objects.filter(user=user).select_related("material")
        ],
        "consentimentos": [
            {
                "finalidade": registro.get_purpose_display(),
                "versao_da_politica": registro.policy_version,
                "aceito_em": registro.granted_at,
                "revogado_em": registro.revoked_at,
            }
            for registro in ConsentRecord.objects.filter(user=user)
        ],
        "registros_de_seguranca": {
            "acessos_realizados": [
                {
                    "entrada": acesso.attempt_time,
                    "saida": acesso.logout_time,
                    "endereco_ip": acesso.ip_address,
                    "navegador": acesso.user_agent,
                }
                for acesso in acessos
            ],
            "tentativas_de_acesso_malsucedidas": [
                {
                    "ultima_tentativa": tentativa.attempt_time,
                    "quantidade": tentativa.failures_since_start,
                    "endereco_ip": tentativa.ip_address,
                    "navegador": tentativa.user_agent,
                }
                for tentativa in tentativas
            ],
            "recuperacao_de_senha": [
                {
                    "evento": evento.get_event_display(),
                    "data": evento.created_at,
                    "endereco_ip": evento.ip_address,
                }
                for evento in PasswordResetLog.objects.filter(user=user)
            ],
        },
    }


def excluir_conta(user):
    """Exclui a conta e os dados pessoais ligados a ela.

    Tudo acontece dentro de uma transação: se qualquer etapa falhar, nada é
    apagado, e a pessoa não fica com metade dos dados removida.

    O que sai e o que fica:

    - conta, hash da senha, segredo do 2FA e tokens de recuperação: apagados
      (os três últimos em cascata, junto com a conta);
    - registros do django-axes: apagados, porque são identificados pelo e-mail
      e não servem para nada sem a pessoa a quem se referem;
    - trilha de recuperação de senha: anonimizada. O evento e a data ficam, mas
      o IP e o navegador são apagados e o vínculo com a conta vira nulo. Sobra a
      contagem do que aconteceu, sem nada que aponte para alguém;
    - materiais guardados na conta: apagados em cascata junto com ela. São
      preferência da pessoa, e preferência sem dono não serve para nada;
    - registros de consentimento: marcados como revogados e desvinculados da
      conta. Ficam só finalidade, versão e datas;
    - trilha de autenticação (AuthEvent): o vínculo com a conta vira nulo, e
      nada mais é alterado. IP, navegador e o identificador selado continuam
      lá porque entram no cálculo do hash de cada registro: apagá-los mudaria
      o conteúdo de linhas já gravadas e quebraria a cadeia inteira, fazendo o
      sistema acusar adulteração onde só houve um pedido de exclusão.

      Essa é uma tensão real entre minimizar dados e manter a trilha
      verificável, e está escrita em docs/analise-de-logs.md junto com a
      pendência de retenção, que é o que resolveria o caso: apagar os
      registros antigos por idade, e não por pessoa.
    """
    with transaction.atomic():
        # Revogar antes de excluir: a data de revogação é a prova de que o
        # tratamento terminou por vontade do titular.
        ConsentRecord.revogar_todos(user)

        PasswordResetLog.objects.filter(user=user).update(ip_address=None, user_agent="")

        for modelo in (AccessAttempt, AccessLog, AccessFailureLog):
            modelo.objects.filter(username__iexact=user.email).delete()

        # O delete dispara as cascatas (2FA, tokens) e anula os vínculos dos
        # modelos com SET_NULL (trilha de recuperação e consentimentos).
        user.delete()
