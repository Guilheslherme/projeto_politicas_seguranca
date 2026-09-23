// Botão de mostrar e esconder a senha.
//
// Alguns navegadores desenham um olho próprio dentro do campo, mas nem todos,
// e só enquanto a pessoa digita. Este fica sempre visível, ao lado do campo.
//
// O botão é montado aqui, e não escrito no template, porque assim vale para
// todo campo de senha de qualquer tela que carregue este arquivo, sem repetir
// o mesmo desenho do olho em cada formulário.

// Os dois desenhos usam currentColor, então eles acompanham a cor do botão.
const OLHO_ABERTO =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"' +
  ' stroke-linecap="round" aria-hidden="true">' +
  '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"/>' +
  '<circle cx="12" cy="12" r="3"/></svg>';

const OLHO_FECHADO =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"' +
  ' stroke-linecap="round" aria-hidden="true">' +
  '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"/>' +
  '<circle cx="12" cy="12" r="3"/><path d="M3 3l18 18"/></svg>';

document.querySelectorAll('input[type="password"]').forEach(function (campo) {
  // Põe o campo e o botão lado a lado, dentro de uma caixa.
  const caixa = document.createElement('div');
  caixa.className = 'campo-senha';
  campo.parentNode.insertBefore(caixa, campo);
  caixa.appendChild(campo);

  const botao = document.createElement('button');
  botao.type = 'button';
  botao.className = 'olho';
  botao.setAttribute('aria-label', 'Mostrar a senha');
  botao.innerHTML = OLHO_ABERTO;
  caixa.appendChild(botao);

  botao.addEventListener('click', function () {
    // A senha aparece quando o campo deixa de ser do tipo "password" e passa
    // a ser um campo de texto comum.
    const estaVisivel = campo.type === 'text';
    campo.type = estaVisivel ? 'password' : 'text';
    botao.innerHTML = estaVisivel ? OLHO_ABERTO : OLHO_FECHADO;
    botao.setAttribute('aria-label', estaVisivel ? 'Mostrar a senha' : 'Esconder a senha');
  });
});
