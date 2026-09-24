# Ideia do projeto — Parte 1: meu primeiro assistente de IA no ar

> Este texto conta, em linguagem simples, o que eu quero construir.
> Não é preciso saber programar para escrevê-lo. No final há um prompt para pedir ao Claude Code (ou ao Codex) que transforme esta ideia numa spec técnica.

## O que eu quero

Quero colocar na internet um chat com inteligência artificial que responda dúvidas sobre um assunto que eu escolher. Qualquer pessoa deve conseguir abrir um link e conversar com ele.

No meu caso, o assistente vai ajudar alunos com dúvidas sobre **engenharia de dados e Inteligência Artificial**, explicando de forma didática, como um professor.

## Qual IA eu quero usar

Quero que o assistente funcione com a chave que eu tiver: **OpenRouter**, **Anthropic** ou **OpenAI**.

- O OpenRouter é o meu preferido: com uma única conta ele dá acesso a modelos de vários fornecedores, inclusive **gratuitos** (os que terminam em `:free`, como `google/gemma-4-31b-it:free`).
- Se eu tiver mais de uma chave, quero escolher a ordem de preferência. Se o primeiro falhar (modelo gratuito lotado, sem crédito, fora do ar), o assistente deve tentar o próximo sozinho.
- Se nenhum funcionar, quero ver no chat o motivo de cada falha.

## Como eu quero personalizar

Não quero mexer em código para mudar o assistente. Quero **um único arquivo de configuração** onde eu consiga trocar:

- o nome do assistente e uma frase de descrição;
- as cores da página (uma ou duas cores);
- a logo e o tamanho dela;
- quais provedores e modelos ele usa, em ordem de preferência, e o tamanho máximo das respostas;
- as instruções de comportamento: quem ele é, com quem fala, o que ele não deve fazer;
- algumas perguntas de exemplo que aparecem como botões para o usuário clicar.

Quero editar esse arquivo pelo próprio site do GitHub, sem instalar nada.

## Como eu quero publicar

- O código fica no **GitHub**.
- O chat fica publicado de graça no **Hugging Face Spaces**.
- Toda vez que eu salvar uma alteração no GitHub, o site deve **atualizar sozinho**.
- Antes de publicar, alguma coisa precisa **conferir se eu não errei na configuração** (uma cor que não existe, um campo vazio, uma logo que não está lá). Se eu errar, a publicação para e o site antigo continua no ar, com uma mensagem dizendo o que corrigir.

## Segurança

- As chaves de API **não podem aparecer no código** nem no GitHub. Elas devem ficar guardadas nas configurações do Hugging Face.
- Se alguém colocar uma chave no código por engano, a publicação deve ser bloqueada.

## Aparência

- A página deve ter a logo, o nome e a descrição no topo.
- O fundo deve usar as cores que escolhi, e o chat deve ficar fácil de ler.
- Tudo o que aparece na tela deve estar em português.

## O que NÃO entra agora

- Base de conhecimento com os meus próprios documentos (fica para a parte 2).
- Um site próprio, com domínio próprio e visual feito do zero (fica para a parte 3).
- Login de usuários e conversas salvas.

## Como vou saber que deu certo

- Eu abro o link e converso com o assistente.
- Eu mudo uma cor ou uma pergunta de exemplo pelo GitHub, e minutos depois o site mostra a mudança.
- Eu erro de propósito na configuração, a publicação é barrada e o site antigo continua funcionando.

---

## Prompt para gerar a spec

Copie o texto abaixo e cole no Claude Code ou no Codex, na mesma pasta deste arquivo:

```

