// Modal de consentimento da tela de cadastro.
//
// A janela em si é a tag <dialog> do HTML, que já traz o fundo escurecido, o
// fechar com Esc e o foco preso dentro dela. O que está aqui é só o que é do
// projeto: liberar o botão, marcar a caixa do formulário e registrar o envio.

const modal = document.querySelector('#modal-saude');
const caixaDoModal = document.querySelector('#modal-aceite');
const botaoContinuar = document.querySelector('#modal-continuar');

// Esta é a caixa de verdade, a do formulário do Django. O modal não cria campo
// novo: ele só explica e depois marca esta.
const caixaDoFormulario = document.querySelector('#id_accept_privacy_policy');

// Abre sozinho, porque a explicação tem que vir antes do aceite.
modal.showModal();

// O botão só libera depois da caixa marcada.
caixaDoModal.addEventListener('change', function () {
  botaoContinuar.disabled = !caixaDoModal.checked;
});

botaoContinuar.addEventListener('click', function () {
  caixaDoFormulario.checked = true;

  // Envio simulado. No cadastro ainda não existe user_id, porque a conta só
  // nasce quando o formulário é enviado. O registro que vale de verdade é o
  // ConsentRecord, gravado no servidor junto com a criação da conta.
  console.log('consentimento (simulado):', {
    user_id: null,
    timestamp: new Date().toISOString(),
    versao_do_termo: 'v1.0-saude'
  });

  modal.close();
});

// Fechar sem aceitar tem que ser possível: consentimento forçado é nulo.
document.querySelector('#modal-fechar').addEventListener('click', function () {
  modal.close();
});

document.querySelector('#abrir-modal').addEventListener('click', function () {
  modal.showModal();
});
