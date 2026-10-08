# Ideia do projeto — Parte 3: front-end próprio e deploy em produção

> Este texto conta, em linguagem simples, o que eu quero acrescentar ao assistente das Partes 1 e 2.
> No final há um prompt para pedir ao Claude Code (ou ao Codex) que transforme esta ideia numa spec técnica.

## O que eu quero

Hoje o assistente funciona, mas tem cara de protótipo: a interface é a padrão do Gradio e ele mora no Hugging Face. Quero dar a ele **cara de produto**: uma interface própria, bonita e moderna, publicada num endereço próprio, com um deploy mais robusto. E quero que a base de conhecimento passe a aceitar também **PDF**, não só Markdown.

## Como eu quero que a interface seja

- Bonita e moderna, no nível dos chats comerciais, com as cores e a logo do meu `config.yml`.
- Resposta aparecendo aos poucos (streaming), como hoje.
- As **fontes** de cada resposta aparecem como cartões clicáveis: ao abrir, mostram o trecho do material que foi usado.
- Perguntas de exemplo como sugestões na tela inicial.
- Funciona bem no celular.
- Modo claro e modo escuro.
- Estados bem resolvidos: tela inicial vazia, carregando, erro, e a resposta "não encontrei".
- Tudo em português.

## Como eu quero que funcione por trás

- O navegador **nunca** recebe chave nenhuma. Ele só manda a pergunta e recebe a resposta com as fontes.
- O servidor faz o que o `app.py` faz hoje: busca os trechos no Supabase, monta o prompt e chama o provedor de IA.
- Um único endereço serve a interface e a API.
- Proteção básica contra abuso: limite de tamanho da pergunta e de perguntas por minuto, para ninguém gastar a minha chave.

## Documentos em PDF

- Quero poder colocar arquivos `.pdf` na pasta `documentos/`, junto com os `.md`.
- Na indexação, o PDF é convertido para Markdown automaticamente, sem cabeçalhos, rodapés e números de página repetidos.
- PDF escaneado (só imagem, sem texto) não precisa funcionar agora: basta o portão avisar com uma mensagem clara.
- As perguntas de teste continuam conferindo se a busca encontra o trecho certo, inclusive nos PDFs.

## Onde eu quero publicar

- No **Railway**, num endereço como `professor-nta.up.railway.app`, com HTTPS.
- O deploy continua passando pelo portão: o GitHub Actions testa, avalia a busca e só então manda o Railway publicar. Nada de publicar sozinho a cada commit sem teste.
- Depois do deploy, alguma coisa confere se o site novo está de pé e respondendo.
- A configuração do Railway fica num arquivo do repositório, não só em cliques no painel.
- O Space do Hugging Face deixa de ser o destino do deploy.

## O que NÃO entra agora

- Login de usuários e conversas salvas.
- Enviar documentos pela interface do chat (os documentos continuam entrando pelo repositório).
- Domínio próprio (fica o subdomínio do Railway).
- OCR para PDF escaneado.
- Pagamento, planos ou painel administrativo.

## Como vou saber que deu certo

- Abro `https://<meu-servico>.up.railway.app` e vejo uma interface bonita, com a minha logo e as minhas cores, no computador e no celular.
- Pergunto algo do material e a resposta chega aos poucos, com cartões de fonte que mostram o trecho usado.
- Coloco um PDF na pasta `documentos/`, faço commit, e o assistente passa a responder sobre ele.
- Abro o código-fonte da página no navegador e não encontro chave nenhuma.
- Coloco uma pergunta de teste impossível e o deploy é barrado; o site no ar continua funcionando.
- Mando perguntas demais em sequência e o servidor pede para esperar, em vez de gastar a chave sem limite.

---

## Prompt para gerar a spec

Copie o texto abaixo e cole no Claude Code ou no Codex, na pasta do repositório:

```
Leia os arquivos IDEIA-parte3.md, SPEC-parte1-cicd-deploy.md e SPEC-parte2-rag.md.
As specs das partes 1 e 2 já estão implementadas; a ideia descreve o que eu quero agora.

Antes de escrever qualquer coisa, me faça as perguntas que faltarem para você
decidir (por exemplo: qual biblioteca de interface usar, o nome do serviço no Railway,
o plano do Railway, os limites de uso). Faça no máximo 5 perguntas, uma lista só.

Depois, gere o arquivo SPEC-parte3-frontend-producao.md no mesmo formato das specs anteriores, com:
1. Objetivo, escopo e o que fica fora
2. Arquitetura: o que roda no navegador, no servidor, no Supabase e no GitHub Actions
3. Stack do front-end e do servidor, e restrições conhecidas do Railway
4. Arquivos novos, alterados e removidos
5. Contrato da API: cada rota, o que recebe, o que devolve e os erros
6. Requisitos funcionais da interface e do servidor, continuando a numeração
7. Como os PDFs entram na base de conhecimento
8. Segurança: onde ficam as chaves, limites de uso e o que nunca pode ir para o navegador
9. Novas verificações do portão, continuando a numeração
10. Pipeline de deploy no Railway, a configuração no repositório e a verificação depois do deploy
11. Critérios de aceite em formato de checklist
12. Ordem das tarefas de implementação, uma de cada vez
13. Erros comuns e como resolver

Não altere o que as partes 1 e 2 já garantem: os testes delas continuam valendo.
Escreva em português, para um iniciante entender.
Não escreva código ainda: só a spec. Quando terminar, me mostre o resumo e
espere a minha aprovação.
```

Depois de aprovar a spec, peça: **"Implemente a tarefa 1 da spec e me mostre como testar."** Siga assim, uma tarefa por vez.
