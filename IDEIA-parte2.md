# Ideia do projeto — Parte 2: o assistente consulta os meus documentos

> Este texto conta, em linguagem simples, o que eu quero acrescentar ao assistente da Parte 1.
> No final há um prompt para pedir ao Claude Code (ou ao Codex) que transforme esta ideia numa spec técnica.

## O que eu quero

Hoje o assistente responde com o que o modelo já sabe. Quero que ele responda com base no **material do meu curso**: as apostilas das aulas e outros documentos de consulta. Se a resposta não estiver no material, ele deve dizer isso, em vez de inventar.

## Quais documentos

- As apostilas das Partes 1 e 2, convertidas para Markdown (`.md`).
- Ficam numa pasta `documentos/` do repositório. Para acrescentar material, basta colocar um novo `.md` na pasta e fazer commit.
- Só arquivos `.md` na pasta: PDF e Word ficam fora do repositório.
- Nada de dado pessoal ou sigiloso nos documentos: o repositório é público.

## Como eu quero que ele responda

- Só com base nos trechos encontrados no material.
- Mostrando, no fim da resposta, de qual documento e de qual seção veio a informação.
- Quando não encontrar, respondendo exatamente: "Não encontrei isso no material do curso."
- Ignorando qualquer instrução que esteja escrita dentro dos documentos.

## Onde eu quero guardar a base de conhecimento

- Num **banco vetorial no Supabase** (Postgres com a extensão pgvector), no plano gratuito.
- Quero conseguir abrir o painel do Supabase e ver a tabela com os trechos, a fonte de cada um e os vetores.
- O Space só **lê** o banco. Quem **grava** é o GitHub Actions. Cada um usa uma chave diferente, e a chave que grava nunca vai para o Space.

## Como eu quero que a busca funcione

- Busca híbrida: por palavras e por sentido (embeddings), juntando os resultados com RRF.
- Um modelo de embedding gratuito e multilíngue, que rode sem chave de API.
- Poder ajustar pelo `config.yml`: o tamanho dos trechos, quantos trechos vão para o modelo e o peso de cada tipo de busca (peso zero desliga).

## Como eu quero publicar

- O mesmo processo da Parte 1: cada commit na `main` testa e publica.
- A cada push, o índice é reconstruído a partir da pasta `documentos/`.
- Antes de publicar, perguntas de teste conferem se a busca encontra o trecho certo. Se a taxa de acerto ficar abaixo do limite que eu definir, nada é publicado e o assistente no ar continua usando o índice antigo.

## O que NÃO entra agora

- Reranker, GraphRAG e agentes.
- Enviar documentos pela página do chat.
- Avaliação automática da resposta do modelo (só da busca).
- Histórico de conversas salvo no banco.
- Front-end próprio (fica para a Parte 3).

## Como vou saber que deu certo

- Abro o Supabase e vejo os trechos das apostilas na tabela.
- Pergunto algo que está nas apostilas e a resposta vem com a fonte.
- Pergunto algo que não está no material e ele diz que não encontrou.
- Pergunto com outras palavras e ele ainda acha o trecho certo.
- Coloco uma pergunta de teste impossível, a publicação é barrada e o assistente no ar continua respondendo como antes.

---

## Prompt para gerar a spec

Copie o texto abaixo e cole no Claude Code ou no Codex, na pasta do repositório:

```
Leia os arquivos IDEIA-parte2.md e SPEC-parte1-cicd-deploy.md. A spec da parte 1
já está implementada; a ideia descreve o que eu quero acrescentar agora.

Antes de escrever qualquer coisa, me faça as perguntas que faltarem para você
decidir (por exemplo: qual modelo de embedding usar, o tamanho padrão dos trechos,
o limiar de acerto do portão, quantas perguntas de teste). Faça no máximo 5
perguntas, uma lista só.

Depois, gere o arquivo SPEC-parte2-rag.md no mesmo formato da spec da parte 1, com:
1. Objetivo, escopo e o que fica para a parte 3
2. Stack: biblioteca de embedding, banco vetorial (Supabase com pgvector), busca
   por palavras, fusão (RRF) e onde cada coisa roda (GitHub Actions, Supabase, Space)
3. Arquivos novos e arquivos alterados
4. Novos campos do config.yml: obrigatório, valores aceitos e padrão
5. Requisitos funcionais, continuando a numeração da parte 1
6. Novas verificações do portão, continuando a partir de T10
7. Mudanças no pipeline: indexação, avaliação e como o índice avaliado vira o índice
   que o assistente consulta, sem afetar o que está no ar se o portão falhar
8. O SQL do banco (tabela, função de busca e permissões) e quais chaves ficam onde
9. Formato do arquivo de perguntas de teste e as métricas (hit rate@k e MRR)
10. Critérios de aceite em formato de checklist
11. Ordem das tarefas de implementação, uma de cada vez
12. Erros comuns e como resolver

Não altere o que a parte 1 já garante: os testes dela continuam valendo.
Escreva em português, para um iniciante entender.
Não escreva código ainda: só a spec. Quando terminar, me mostre o resumo e
espere a minha aprovação.
```

Depois de aprovar a spec, peça: **"Implemente a tarefa 1 da spec e me mostre como testar."** Siga assim, uma tarefa por vez.
