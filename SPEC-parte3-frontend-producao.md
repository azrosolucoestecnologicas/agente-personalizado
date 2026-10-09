# SPEC — Parte 3: interface própria, PDF na base e deploy em produção no Railway

> Continuação das specs `SPEC-parte1-cicd-deploy.md` e `SPEC-parte2-rag.md`, que já estão implementadas e no ar.
> Esta spec diz **o que** construir e **como conferir**. O código vem depois, uma tarefa por vez (seção 12).
> Base: `IDEIA-parte3.md` e a apostila "Parte 3: Front-end com IA e Produção".

**Decisões já tomadas com você:**

| Pergunta | Decisão |
|---|---|
| Biblioteca da interface | **React + Vite + TypeScript + Tailwind**, compilada dentro da imagem e servida pelo mesmo servidor Python (**FastAPI**) |
| Railway | Projeto **novo** `professor-nta`, endereço `professor-nta.up.railway.app`, plano **Hobby** (o modelo de embedding precisa de ~1,5 GB de memória) |
| Limites de uso | Por visitante (IP): **10 perguntas por minuto** e **100 por dia**; pergunta de até **2.000 caracteres** (o limite que já existe) |
| Space do Hugging Face | **Pausado** depois que o Railway estiver no ar e aprovado |
| PDF de teste | A apostila da Parte 3 (`Apostila_Parte3_Frontend_Producao.pdf`), que vira o 3º documento da base |

## Glossário rápido

| Termo | Em uma frase |
|---|---|
| **Front-end** | A parte que roda no navegador: o que o aluno vê e clica. É pública: qualquer um lê o código dela. |
| **Back-end / servidor** | A parte que roda no Railway: busca no Supabase, guarda as chaves e chama a IA. |
| **API** | As "portas" do servidor (`/api/...`), cada uma com um contrato: o que recebe e o que devolve. |
| **SSE (Server-Sent Events)** | Uma resposta HTTP que fica aberta e vai recebendo pedaços, que é como a resposta aparece aos poucos. |
| **React / Vite / Tailwind** | Biblioteca de componentes de tela / ferramenta que compila o front-end / classes prontas de estilo. |
| **FastAPI** | Biblioteca Python para APIs. Valida a entrada sozinha (com Pydantic). |
| **Docker / imagem** | Receita (`Dockerfile`) que monta um pacote com sistema, Python, bibliotecas, modelo e código. Roda igual em qualquer lugar. |
| **Railway** | A plataforma onde o serviço fica no ar (PaaS), com HTTPS, logs, *health check* e *rollback*. |
| **Wait for CI** | Opção do Railway que só publica um commit **depois** que o GitHub Actions passou. É ela que liga o Railway ao portão. |
| **Health check** | Rota (`/api/saude`) que o Railway chama antes de trocar a versão. Se ela não responde, a versão antiga continua no ar. |
| **Rate limit (limite de uso)** | Quantas perguntas um visitante pode fazer por minuto e por dia. Passou disso, o servidor responde "aguarde" (429). |

---

## 1. Objetivo, escopo e o que fica fora

### 1.1 Objetivo
Dar ao assistente **cara de produto**:
- uma interface própria, moderna, com a logo e as cores do `config.yaml`;
- num endereço próprio com HTTPS, no Railway;
- com o **mesmo portão** das Partes 1 e 2: nada vai para o ar sem passar nos testes e na avaliação da busca;
- e com a base de conhecimento aceitando **PDF**, além de Markdown.

### 1.2 O que entra na Parte 3
1. **Interface React** com:
   - streaming;
   - **cartões de fonte** clicáveis, que mostram o trecho usado;
   - sugestões na tela inicial;
   - modo claro e escuro;
   - funcionamento no celular;
   - todos os estados resolvidos: vazio, pensando, erro, "não encontrei" e limite de uso;
   - tudo em português.
2. **Servidor FastAPI** com três rotas: `/api/saude`, `/api/config` e `/api/perguntar`. É o mesmo servidor que entrega a interface, num **único endereço**.
3. **Limites de uso no servidor**: 413 para pergunta grande demais e 429 para perguntas demais, com tempo de espera.
4. **PDF em `documentos/`**, convertido para Markdown na indexação, sem cabeçalhos, rodapés e números de página repetidos. PDF escaneado é barrado com mensagem clara.
5. **Docker** em dois estágios (Node compila a interface; Python roda o servidor com o modelo dentro da imagem).
6. **`railway.json`** no repositório: a configuração do Railway versionada.
7. **Railway com Wait for CI**: só publica commit que passou no portão.
8. **Verificação depois do deploy**: um job confere se o site novo está de pé, na versão certa e sem chave no código da página.
9. O **Space do Hugging Face deixa de ser o destino** do deploy e é pausado no fim.

### 1.3 O que NÃO entra agora
- Login de usuários e conversas salvas (a conversa vive só na aba do navegador, como hoje).
- Enviar documentos pela interface (continuam entrando pelo repositório).
- Domínio próprio (fica o `professor-nta.up.railway.app`).
- OCR para PDF escaneado.
- Pagamento, planos ou painel administrativo.

---

## 2. Arquitetura: o que roda onde

```
 Navegador (público)                 Railway: 1 serviço, 1 contêiner              Supabase
┌──────────────────────┐  HTTPS    ┌─────────────────────────────────────┐      ┌───────────────────┐
│ Interface React      │ ───────►  │  /        → interface compilada     │      │ trechos (producao)│
│ (arquivos estáticos) │           │  /api/... → FastAPI                 │ ───► │ buscar_hibrido()  │
│ só conhece /api      │ ◄───────  │    · busca no Supabase (publicável) │      └───────────────────┘
│ NENHUMA chave        │  SSE      │    · monta o prompt (Parte 2)       │      ┌───────────────────┐
└──────────────────────┘           │    · chama a IA com troca automática│ ───► │ OpenRouter /      │
                                   │  chaves só em Variables do Railway  │      │ Anthropic / OpenAI│
                                   └─────────────────────────────────────┘      └───────────────────┘

 GitHub Actions (o portão continua decidindo)
   push na main ──► testes (Python + interface + imagem) ──► avaliar (índice + T25) ──► promover (teste → producao)
                                                                                          │ tudo verde?
   Railway (Wait for CI): só então monta a imagem e publica ◄──────────────────────────────┘
   depois do deploy ──► verificar-producao: /api/saude, versão certa, nenhuma chave na página
```

| Lugar | O que roda | O que guarda |
|---|---|---|
| **Navegador** | Interface React compilada (HTML, CSS, JS) | Só a conversa da aba aberta e a preferência de tema. **Nenhuma chave, prompt de sistema ou nome de modelo.** |
| **Railway** | Contêiner com FastAPI (`uvicorn`), o modelo de embedding e a interface compilada | Chaves de IA e chave **publicável** do Supabase, em *Variables* |
| **Supabase** | Tabela `trechos` e função `buscar_hibrido` (Parte 2, sem mudanças) | Os trechos das coleções `teste` e `producao` |
| **GitHub Actions** | Testes, build da interface, build da imagem, indexação, avaliação e promoção | Chave **secreta** do Supabase (só aqui, como hoje) |

**O fluxo de uma pergunta** é o mesmo da Parte 2. Muda só a "porta de entrada": em vez do Gradio, a rota `POST /api/perguntar`, que devolve os eventos em SSE.

---

## 3. Stack e restrições conhecidas do Railway

| Peça | Escolha | Observação |
|---|---|---|
| Interface | **React 18 + TypeScript**, montada com **Vite**, estilos com **Tailwind CSS** | Poucas dependências. Markdown das respostas com `react-markdown` + `remark-gfm` (tabelas), que **não executa HTML** vindo do texto. |
| Testes da interface | **Vitest** + Testing Library | Rodam sem navegador real e sem servidor (a API é simulada). |
| Servidor | **FastAPI** + **uvicorn**, Python **3.12** | A apostila usa 3.11; seguimos com 3.12, a mesma versão das Partes 1 e 2. |
| Streaming | **SSE** pela `StreamingResponse` do FastAPI | Sem biblioteca extra. |
| Lógica de IA, RAG e banco | Os módulos atuais: `agente/provedores.py`, `roteador.py`, `rag.py`, `banco.py`, `embeddings.py` | Reaproveitados. O roteador passa a devolver **eventos** (texto, fontes, fim) em vez de texto com as fontes coladas no fim. |
| Conversão de PDF | **pymupdf4llm** (já usada para converter as apostilas na Parte 2) | Licença **AGPL**: roda **só na indexação** (GitHub Actions) e **não vai para a imagem** do servidor. |
| Imagem | **Dockerfile em dois estágios**: `node:24` compila a interface; `python:3.12-slim` recebe o resultado | Node 24 é a versão LTS atual (o Node 20 da apostila saiu de suporte em abril de 2026). O modelo de embedding é **baixado no build** e fica dentro da imagem. |
| Hospedagem | **Railway**, plano Hobby, região padrão | Um serviço só: interface e API no mesmo endereço, sem CORS. |

**Restrições do Railway que a spec respeita:**
- **Porta:** o Railway informa a porta na variável `PORT`, e o servidor precisa escutar nela (`0.0.0.0:$PORT`).
- **Memória:** o e5-base ocupa ~1,1 GB em disco e ~1,5 GB em memória. Por isso o plano Hobby, que vai até 8 GB. O build roda em máquinas separadas do Railway (o problema de memória da apostila com o Render não se repete).
- **Variáveis:** as chaves ficam em *Variables* do serviço. Mudar uma variável gera um novo deploy.
- **Wait for CI** só funciona com o serviço ligado ao repositório do GitHub (*Deploy from GitHub repo*), na branch `main`.
- **Health check:** o Railway chama `/api/saude` depois de subir a versão nova e espera até 300 s. Se não vier 200, a versão antiga continua no ar.
- **IP do visitante:** o Railway fica na frente do servidor (proxy). O IP real vem no cabeçalho `X-Forwarded-For`, e é por ele que o limite de uso é contado.
- **Um contêiner só:** os contadores do limite de uso ficam na memória. Se o serviço reiniciar, eles zeram, o que é aceitável para este uso.
- **Custo:** o Railway cobra pelo uso de memória e CPU. A aba *Metrics* mostra o consumo.

---

## 4. Arquivos novos, alterados e removidos

```
agente-personalizado/
├── frontend/                           🆕 a interface
│   ├── package.json / package-lock.json    dependências travadas (npm ci)
│   ├── vite.config.ts                  em desenvolvimento, /api vai para a porta 8000
│   ├── tailwind.config.ts, index.html, tsconfig.json
│   └── src/
│       ├── main.tsx, App.tsx
│       ├── api.ts                      fala com /api (config e perguntar em SSE)
│       ├── tipos.ts                    tipos do contrato da API (seção 5)
│       ├── components/                 Cabecalho, Sugestoes, Conversa, Mensagem, CartaoFonte,
│       │                               CaixaPergunta, AlternarTema, Aviso
│       └── __tests__/                  T28
├── agente/
│   ├── servidor.py                     🆕 FastAPI: rotas /api e entrega da interface
│   ├── limites.py                      🆕 limite de tamanho e de perguntas por minuto/dia
│   ├── pdf.py                          🆕 PDF → Markdown (só na indexação)
│   ├── roteador.py                     ✏️ devolve eventos (fontes, texto, fim, erro)
│   ├── documentos.py                   ✏️ aceita .pdf; valida PDF (escaneado, tamanho)
│   ├── config.py                       ✏️ bloco "servidor" (limites de uso)
│   ├── interface.py                    🗑️ a tela Gradio sai
│   └── (provedores, rag, banco, embeddings, perguntas, segredos continuam)
├── documentos/
│   └── parte3-frontend-producao.pdf    🆕 a apostila da Parte 3
├── perguntas_teste.yaml                ✏️ + 6 perguntas sobre o PDF
├── Dockerfile, .dockerignore           🆕 imagem em dois estágios
├── railway.json                        🆕 o serviço do Railway como código
├── requirements.txt                    ✏️ servidor: sai gradio e spaces, entram fastapi e uvicorn
├── requirements-indice.txt             🆕 indexação: fastembed + pymupdf4llm (não vai para a imagem)
├── requirements-dev.txt                ✏️ testes
├── app.py                              🗑️ sai (o ponto de entrada passa a ser agente/servidor.py)
├── scripts/
│   ├── publicar.py                     🗑️ sai (era o envio ao Hugging Face)
│   ├── verificar_producao.py           🆕 confere o site no ar depois do deploy (T32)
│   └── indexar.py, avaliar.py ...      ✏️ indexar lê PDF; o resto continua
├── tests/                              ✏️ ajustes listados na seção 9.2; novos test_servidor.py, test_pdf.py, ...
├── .github/workflows/
│   ├── deploy.yml                      ✏️ testes → avaliar → promover (sai o envio ao Space)
│   └── verificar.yml                   🆕 roda depois de cada deploy do Railway
├── README.md                           ✏️ sai o cabeçalho do Hugging Face; entra "como rodar e publicar"
└── SPEC-parte3-…md, ACEITE-parte3.md   📄 documentação
```

**O que sai e por quê:** o Gradio, o `spaces` (ZeroGPU), o `app.py`, a `interface.py` e o `publicar.py` só existiam para o Space do Hugging Face. A lógica que importa (provedores, troca automática, RAG, proteção das chaves) **continua** e passa a ser chamada pelo servidor FastAPI.

---

## 5. Contrato da API

Todas as rotas ficam em `/api`. A interface chama **só** caminhos relativos (`/api/...`) e nunca um provedor de IA diretamente.

### 5.1 `GET /api/saude`: o servidor está pronto?
Usada pelo **health check do Railway** e pela verificação depois do deploy.

| Situação | Status | Corpo |
|---|---|---|
| Pronto | **200** | `{"status": "ok", "versao": "a1b2c3d", "trechos_na_producao": 178}` |
| Base de conhecimento ligada, mas sem `SUPABASE_URL`/`SUPABASE_PUBLISHABLE_KEY`, banco fora do ar ou modelo que não carregou | **503** | `{"status": "indisponivel", "versao": "a1b2c3d", "motivo": "faltam as variáveis SUPABASE_URL..."}` |

- `versao` = os 7 primeiros caracteres de `RAILWAY_GIT_COMMIT_SHA`, que o Railway informa (`"local"` no computador).
- A contagem de trechos é guardada por 60 s, para o health check não consultar o banco a cada chamada.
- O motivo **nunca** contém chave (passa pela limpeza da Parte 1).

### 5.2 `GET /api/config`: o que a interface precisa saber
**200**
```json
{
  "nome": "Professor de Dados & IA",
  "descricao": "Tire suas dúvidas sobre o material do curso...",
  "exemplos": ["O que é CI/CD?", "..."],
  "logo_url": "/api/logo",
  "cores": {"principal": "#132A5C", "secundaria": "#27488F", "destaque": "#E0262B"},
  "limites": {"max_caracteres_pergunta": 2000},
  "mensagem_nao_encontrado": "Não encontrei isso no material do curso."
}
```
**Nunca** contém: `instrucoes` (o prompt de sistema), nomes de provedores ou de modelos, temperatura, chaves, endereço do Supabase.

### 5.3 `GET /api/logo`: a logo do `config.yaml`
**200** com o arquivo (`image/svg+xml` ou `image/png`), com cache de 1 hora. **404** se o arquivo sumir.

### 5.4 `POST /api/perguntar`: a pergunta, respondida em streaming
**Recebe** (JSON):
```json
{
  "mensagem": "O que é o Wait for CI?",
  "historico": [
    {"papel": "usuario", "texto": "O que é deploy?"},
    {"papel": "assistente", "texto": "Deploy é publicar..."}
  ]
}
```
- `mensagem`: texto, obrigatório, sem ser só espaços.
- `historico`: opcional. Lista de até 20 mensagens, cada uma com `papel` (`usuario` ou `assistente`) e `texto` de até 8.000 caracteres. O servidor usa só as últimas `max_mensagens_historico` (Parte 1).
- **Qualquer outro campo é recusado** (422). Não dá para pedir outro modelo, outra temperatura ou outro prompt.

**Devolve** (`200`, `Content-Type: text/event-stream`), nesta ordem:

| Evento | Quando | Dados |
|---|---|---|
| `fontes` | Logo depois da busca, antes do texto. Só quando há trechos do material | `[{"n": 1, "fonte": "parte3-frontend-producao.pdf", "secao": "10 Railway: o deploy de produção", "trecho": "texto do trecho..."}]` |
| `texto` | Várias vezes, a cada pedaço gerado | `{"delta": "O Wait for CI "}` |
| `fim` | Uma vez, no final | `{"nao_encontrado": false}`: `true` quando a resposta é a frase de "não encontrei"; aí a interface **não** mostra os cartões |
| `erro` | No lugar do `fim`, se não deu para responder | `{"tipo": "provedores", "mensagem": "😕 Não consegui responder agora. Motivos: ..."}` |

Exemplos de cada caso:
- **Cumprimento** ("oi"): só `texto` e `fim`, sem `fontes`.
- **Nada relevante no material:** um único `texto` com a frase exata, seguido de `fim` com `nao_encontrado: true`. A IA **não** é chamada (Parte 2).
- **Falha no meio da resposta:** o texto recebido fica, e chega um `erro` com `tipo: "interrompida"` (regra da Parte 1).
- **Tipos de `erro`:**
  - `provedores`: todos falharam;
  - `interrompida`;
  - `sem_chave`: nenhuma chave de IA configurada;
  - `base_indisponivel`: Supabase fora do ar.

**Erros antes do streaming** (resposta JSON comum, não SSE):

| Status | Quando | Corpo |
|---|---|---|
| **413** | `mensagem` acima de `max_caracteres_pergunta` | `{"erro": "pergunta_longa", "mensagem": "Sua pergunta tem 2.350 caracteres e o limite é 2.000..."}` |
| **422** | JSON inválido, `mensagem` vazia, campo desconhecido, histórico grande demais | `{"erro": "pedido_invalido", "mensagem": "..."}` (em português) |
| **429** | Passou de 10 perguntas por minuto ou 100 por dia **neste IP** | `{"erro": "limite", "mensagem": "Muitas perguntas seguidas. Tente de novo em 40 segundos.", "tentar_em": 40}` + cabeçalho `Retry-After: 40` |
| **503** | Servidor ainda carregando o modelo | `{"erro": "carregando", "mensagem": "O assistente está iniciando. Tente em alguns segundos."}` |

A ordem das verificações é: validação (422) → tamanho (413) → limite de uso (429). Só a pergunta que passa por todas **conta** no limite e chama a busca e a IA.

### 5.5 `/` e demais caminhos: a interface
O servidor entrega `frontend/dist`: `index.html`, JS e CSS. Caminhos desconhecidos fora de `/api` devolvem o `index.html`; os de `/api` desconhecidos devolvem 404 em JSON.

---

## 6. Requisitos funcionais (continuação: RF41 a RF66)

### Interface
- **RF41.** O topo mostra a logo, o nome e a descrição vindos de `/api/config`. A cor principal pinta o cabeçalho, o botão de enviar e os detalhes; o resto da tela usa tons neutros.
- **RF42.** **Tela inicial vazia:** saudação curta e as perguntas de `exemplos` como cartões de sugestão. Clicar envia a pergunta.
- **RF43.** **Mensagens:** as do aluno ficam à direita, na cor principal, com texto em branco ou preto escolhido pelo contraste (como o RF5). As do assistente ficam à esquerda, sem balão, em **Markdown** (listas, negrito, código e tabelas), com largura de leitura de até ~768 px.
- **RF44.** **Pensando:** entre o envio e o primeiro pedaço aparece um indicador animado ("Consultando o material…"), anunciado ao leitor de tela.
- **RF45.** **Streaming:** o texto aparece pedaço por pedaço, conforme os eventos `texto`.
- **RF46.** **Cartões de fonte:** quando há `fontes` e `nao_encontrado` é falso, aparecem abaixo da resposta, numerados, como "documento › seção". Clicar abre o trecho usado; clicar de novo fecha. Funciona por teclado (Enter e Espaço).
- **RF47.** **"Não encontrei":** a frase aparece num estilo neutro, sem cartões, com a dica "Tente perguntar com outras palavras".
- **RF48.** **Erro:** a mensagem do evento `erro`, ou "Sem conexão com o servidor" se a rede cair, aparece com o botão **Tentar de novo**, que reenvia a mesma pergunta. A pergunta nunca se perde.
- **RF49.** **Limite de uso (429):** aviso "Muitas perguntas seguidas. Tente de novo em N segundos", com contagem regressiva. O botão de enviar fica desabilitado até o tempo acabar.
- **RF50.** **Caixa de pergunta:**
  - o campo cresce com o texto, Enter envia e Shift+Enter quebra linha;
  - um contador aparece perto do limite (por exemplo, "1.950/2.000"), e acima do limite o botão fica desabilitado;
  - enquanto responde, o botão vira **Parar**, que interrompe o streaming.
- **RF51.** Botão **Nova conversa**, que limpa a tela. Botão **Copiar** em cada resposta.
- **RF52.** **Modo claro e escuro:** segue a preferência do sistema na primeira visita. O botão alterna e a escolha fica salva no navegador.
- **RF53.** **Celular:** a partir de 360 px de largura, sem rolagem lateral, com a caixa de pergunta fixa embaixo e as sugestões em uma coluna.
- **RF54.** **Acessibilidade:**
  - contraste mínimo AA nos dois temas;
  - tudo utilizável por teclado;
  - rótulos em todos os botões só com ícone;
  - a área da conversa avisa o leitor de tela quando a resposta termina.
- **RF55.** **Tudo em português**, inclusive títulos de aba, rótulos de botão, avisos e mensagens de erro. A página declara `lang="pt-BR"`.
- **RF56.** A interface chama **só** `/api/...` e não guarda chave, prompt de sistema, nome de modelo nem endereço do Supabase. O histórico enviado é o da aba aberta; nada é salvo no navegador além do tema.

### Servidor
- **RF57.** O servidor carrega o `config.yaml` ao iniciar e o valida (Parte 1). Se estiver inválido, não sobe e mostra a lista de erros no log, como o RF1.
- **RF58.** Ao iniciar, o servidor:
  - carrega o modelo de embedding, que está dentro da imagem;
  - conta os trechos da produção;
  - registra no log `Base de conhecimento: N trechos na produção (modelo …)` (RF37).

  Enquanto carrega, `/api/saude` e `/api/perguntar` respondem 503.
- **RF59.** `POST /api/perguntar` usa exatamente a mesma lógica da Parte 2: cumprimentos sem busca, frase exata sem chamar a IA, trechos delimitados, troca automática de provedores e base indisponível. A diferença é que as **fontes viram o evento `fontes`** em vez de texto colado no fim da resposta.
- **RF60.** **Limite de uso**, contado por IP (o primeiro endereço de `X-Forwarded-For`, ou o IP da conexão quando o cabeçalho não existe):
  - `perguntas_por_minuto` (padrão 10) em janela deslizante de 60 s;
  - `perguntas_por_dia` (padrão 100) até a meia-noite UTC.

  Os dois valores ficam no `config.yaml`, bloco `servidor`.
- **RF61.** **Logs** sem conteúdo de pergunta nem chave. Cada pergunta registra:
  - tamanho da pergunta;
  - tipo de resposta (material, conversa, não encontrei, erro);
  - provedor que respondeu;
  - tempo total.

  Também registram cada 429, com o IP mascarado (`200.150.x.x`).
- **RF62.** O servidor responde no máximo **10 perguntas ao mesmo tempo** (como a fila da Parte 1). Acima disso, devolve 503 "muita gente perguntando agora, tente em alguns segundos".

### Base de conhecimento e publicação
- **RF63.** A pasta `documentos/` aceita `.md` e `.pdf` (seção 7).
- **RF64.** O deploy de produção é feito **só pelo Railway**, com **Wait for CI** ligado: um commit na `main` só é publicado se **todos** os jobs do GitHub Actions passarem. O Space do Hugging Face deixa de receber publicações.
- **RF65.** Depois de cada deploy do Railway, o job **verificar-producao** confere:
  - que `/api/saude` responde 200 com a **versão do commit publicado**;
  - que `/api/config` não traz segredo;
  - que a página e os arquivos JS/CSS servidos não contêm nada com formato de chave.
- **RF66.** A configuração do serviço (build pelo Dockerfile, health check, política de reinício) fica no `railway.json` do repositório. Os únicos ajustes feitos no painel são os que não podem ir para arquivo: *Variables*, Wait for CI e o domínio.

### Novo bloco do `config.yaml`
```yaml
servidor:                       # Parte 3: proteção contra abuso (vale no servidor, não só na tela)
  perguntas_por_minuto: 10      # por visitante (IP); 1 a 120
  perguntas_por_dia: 100        # por visitante (IP); 1 a 10000; zera à meia-noite UTC
```
| Campo | Obrigatório | Regra | Padrão |
|---|---|---|---|
| `servidor.perguntas_por_minuto` | Não | Inteiro de 1 a 120 | `10` |
| `servidor.perguntas_por_dia` | Não | Inteiro de 1 a 10.000, maior ou igual ao por minuto | `100` |

> Numa sala de aula, todos podem sair pelo **mesmo IP** da rede. Se aparecerem muitos 429 numa aula, aumente `perguntas_por_minuto` (seção 13).

---

## 7. Como os PDFs entram na base de conhecimento

**Onde:** na indexação (`scripts/indexar.py`, no GitHub Actions). O servidor **não** lê PDF; ele só busca no Supabase, como hoje.

**Passo a passo da conversão (`agente/pdf.py`, com pymupdf4llm):**
1. **Extrair** o texto página por página, já em Markdown. O pymupdf4llm marca os títulos pelo tamanho da fonte e converte tabelas.
2. **Detectar PDF escaneado:** se o documento inteiro tiver menos de 200 caracteres de texto, ou se mais da metade das páginas vier vazia, a indexação **para** com a mensagem: *"❌ parte3.pdf parece ser um PDF escaneado (só imagem): não há texto para extrair. Use um PDF com texto selecionável; OCR fica fora deste projeto."*
3. **Remover cabeçalho e rodapé:** linhas que se repetem em **mais da metade das páginas** saem. Linhas de tabela como `|---|---|` não contam. No PDF de teste, isso remove "INSTITUTO NTA", "Construindo seu Chat de IA Personalizado · Parte 3" e "Material de consulta…".
4. **Remover números de página soltos**, ou seja, linhas que são só um número.
5. **Arrumar os títulos:**
   - tirar o negrito (`## **01 O que…**` vira `## 01 O que…`);
   - juntar espaços repetidos;
   - manter como título só os níveis 1 a 3;
   - níveis 4 a 6 viram texto em negrito. No PDF de teste, esses níveis são legendas de diagrama ("Navegador", "Imagem final") e não seções.
6. **Garantir o título do documento:** se não houver `# …`, usa o título dos metadados do PDF ou o nome do arquivo.
7. **Dividir em trechos** exatamente como os `.md` da Parte 2: por título, com o título repetido no início do trecho e com sobreposição. A `fonte` do trecho é o nome do PDF (`parte3-frontend-producao.pdf`).

**Validação da pasta (amplia o T19):**
- aceita `.md` e `.pdf`;
- cada PDF tem no máximo **20 MB**, não pode estar protegido por senha e precisa ter texto extraível;
- a busca por dados pessoais (e-mail, CPF, telefone) roda sobre o **texto extraído**;
- o nome do arquivo segue a regra atual (minúsculas, números e hífens).

**Comando para conferir antes do commit:** `python scripts/mostrar_trechos.py --filtro "Railway"` passa a mostrar também os trechos dos PDFs. Assim você vê como a conversão ficou.

**Perguntas de teste:** o `perguntas_teste.yaml` ganha **6 perguntas sobre o PDF**, metade com as palavras do texto e metade com outras palavras, apontando para `fonte_esperada: parte3-frontend-producao.pdf`. Se a conversão vier ruim, a busca não acha o trecho, o hit rate cai e o portão barra a publicação.

**Por que pymupdf4llm só na indexação:** ela tem licença AGPL. Roda no GitHub Actions para montar o índice e não faz parte do servidor publicado. Por isso fica no `requirements-indice.txt`, que a imagem do Docker não instala.

---

## 8. Segurança: chaves, limites e o que nunca vai para o navegador

| Segredo / dado | Onde fica | Quem usa | Nunca em |
|---|---|---|---|
| `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | *Variables* do Railway | servidor | navegador, repositório, `railway.json`, imagem, logs |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | *Variables* do Railway | servidor (só lê a produção) | navegador |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | Secrets do GitHub | jobs `avaliar` e `promover` | Railway, navegador, imagem |
| Prompt de sistema (`instrucoes`), provedores e modelos | `config.yaml`, lido pelo servidor | servidor | `/api/config`, navegador |

**Regras que a spec exige:**
1. **Nada de `VITE_` com segredo:** variáveis que começam com `VITE_` são copiadas para dentro do JavaScript público. A interface não usa nenhuma variável de ambiente (nem precisa: chama `/api` relativo).
2. **A API só aceita `mensagem` e `historico`.** Modelo, temperatura e prompt não podem ser enviados pelo navegador (422).
3. **Todo limite vale no servidor.** Desabilitar o botão na interface é só conforto: quem quiser abusar chama a API direto.
4. **Imagem sem segredos:** o `Dockerfile` não recebe chave nenhuma, nem como `ARG` nem como `ENV`. Elas só existem em tempo de execução, nas *Variables*.
5. **Markdown seguro:** as respostas são exibidas sem executar HTML vindo do texto (`react-markdown` sem `rehype-raw`). Um trecho ou resposta com `<script>` aparece como texto.
6. **Cabeçalhos de segurança** em todas as respostas: `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` e uma `Content-Security-Policy` que só permite scripts do próprio endereço.
7. **Logs:** sem texto das perguntas, sem chaves e com o IP mascarado (RF61).
8. **Injeção de prompt por documento:** continua tratada como na Parte 2 (trechos delimitados e instrução para ignorar ordens dentro deles). O PDF passa pelo mesmo caminho.

---

## 9. Verificações do portão

### 9.1 Novas (T26 a T32)

| # | Onde roda | Verificação | O que pega |
|---|---|---|---|
| **T26** | job `testes` (sem rede) | **Contrato da API**, com o cliente de testes do FastAPI e busca/IA simuladas: os eventos de `/api/perguntar` chegam na ordem `fontes → texto… → fim`, os casos 413, 422 e 429 (com `Retry-After`) e 503 respondem certo, e `/api/saude` dá 200/503 | Rota quebrada, contrato mudado sem querer |
| **T27** | job `testes` | **Nada de segredo exposto:** `/api/config` não traz `instrucoes`, provedores, modelos nem chaves (testado com chaves falsas no ambiente); a interface não usa `import.meta.env`/`VITE_`; o `railway.json` e o `Dockerfile` não têm chave | Prompt ou chave vazando para o navegador |
| **T28** | job `interface` (Node) | `npm ci`, verificação de tipos (`tsc --noEmit`), testes Vitest dos componentes e `npm run build`. A varredura de chaves (T8) roda também sobre `frontend/dist` | Interface que não compila, estado quebrado, chave no JS |
| **T29** | job `testes` | **PDF:** a conversão remove cabeçalho, rodapé e número de página, arruma títulos, e um PDF escaneado (sem texto) dá a mensagem clara. O T19 passa a aceitar `.pdf` com as regras da seção 7 | Conversão estragada, PDF ilegível entrando calado |
| **T30** | job `imagem` | **Docker:** a imagem é montada a partir do `Dockerfile` (sem chaves) e sobe. `/api/saude` responde (503 sem Supabase, que é o esperado), `/` entrega a interface e `/api/config` responde | Dockerfile quebrado, `dist` ausente, servidor que não sobe |
| **T31** | job `testes` | **`railway.json`:** builder `DOCKERFILE`, `healthcheckPath: /api/saude`, timeout ≥ 120 s, reinício `ON_FAILURE` e nenhum segredo | Configuração do Railway mexida por engano |
| **T32** | job `verificar-producao` (depois do deploy) | O site no ar responde `/api/saude` com 200 e a **versão do commit publicado**, `/api/config` sem segredo e nenhuma chave no HTML/JS servido | Deploy que subiu a versão errada, ou chave no site publicado |

### 9.2 O que muda nos testes das Partes 1 e 2
As **garantias** continuam todas valendo. Mudam só os testes ligados ao Gradio e ao Hugging Face, que são **substituídos** por equivalentes:

| Antes | Depois |
|---|---|
| **T15**: o app Gradio monta a tela sem chaves e sem rede | **T15**: o servidor FastAPI sobe sem chaves e sem rede, e `/api/perguntar` explica que falta chave (RF15, agora pelo evento `erro` com `tipo: "sem_chave"`) |
| **T16**: cabeçalho do README do Hugging Face e versão do Gradio | **T16**: toda biblioteca usada pelo servidor está no `requirements.txt`, e nenhuma biblioteca de indexação (pymupdf4llm) está nele |
| RF3 a RF7 e RF20/RF21 (tela Gradio, ZeroGPU) | Viram RF41 a RF55 e RF62 da interface React, testados pelo T28. RF21 (ZeroGPU) deixa de existir |
| Testes do `publicar.py` (envio ao Space, secrets do Space) | Saem com o `publicar.py`. A conferência "chave secreta do Supabase nunca no lugar público" continua no T27 e no T22 |
| **T23**: "Fontes consultadas" escritas pelo app no fim do texto | **T23**: as fontes saem no evento `fontes`, e a interface não as mostra quando a resposta é "não encontrei". As outras regras do T23 seguem iguais |
| T1–T14, T17–T22, T24, T25 | **Sem mudança** |

---

## 10. Pipeline de deploy no Railway

```
push na main
   │
   ├─► job "testes"     T1–T27, T29, T31 (Python, sem rede)
   ├─► job "interface"  T28 (Node: tipos, testes, build, chaves no dist)
   └─► job "imagem"     T30 (docker build + sobe o contêiner + 3 chamadas)
            │ todos verdes?   não ──► ❌ para. Railway NÃO publica (Wait for CI).
            ▼
       job "avaliar"     indexa a coleção "teste" (.md e .pdf) + T25
            │ passou?        não ──► ❌ para. "producao" e site intactos.
            ▼
       job "promover"    "teste" vira "producao" (uma transação)
            │
            ▼  (Railway vê o CI verde)
   Railway: monta a imagem pelo Dockerfile → sobe → chama /api/saude
            │ respondeu 200?  não ──► versão antiga continua no ar
            ▼
       troca a versão  ──► GitHub recebe "deployment success"
                                   │
                                   ▼
                     job "verificar-producao" (T32)
```

**Arquivo `railway.json`** (no repositório, sem segredos):
```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "healthcheckPath": "/api/saude",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

**O `Dockerfile` em dois estágios:**
1. **Estágio `interface`** (`node:24-slim`):
   - copia só o `frontend/`;
   - roda `npm ci` e `npm run build`, que gera `frontend/dist`.
2. **Estágio final** (`python:3.12-slim`):
   - instala o `requirements.txt` (servidor, sem pymupdf4llm);
   - **baixa o modelo de embedding** para dentro da imagem;
   - copia `agente/`, `config.yaml`, `assets/` e o `dist` do estágio 1;
   - roda como usuário sem privilégios;
   - inicia com `uvicorn agente.servidor:app --host 0.0.0.0 --port $PORT`.

**O que muda no `deploy.yml`:**
- Novos jobs `interface` e `imagem`, em paralelo com `testes`. O `avaliar` passa a depender dos três.
- O job `publicar` vira **`promover`**: só roda `indexar.py --promover`. Sai o envio ao Space e saem `HF_TOKEN` e `HF_SPACE`.
- O `avaliar` instala `requirements-indice.txt` (fastembed + pymupdf4llm), com o cache do modelo que já existe.
- O botão **Run workflow** fora da `main` roda `testes`, `interface`, `imagem` e `avaliar`, sem promover. Serve para testar um PDF novo sem tocar na `producao`.

**O workflow novo `verificar.yml` (T32):**
- **Quando roda:**
  - **automático:** no evento `deployment_status` com estado `success`, que o Railway envia ao GitHub a cada deploy;
  - **manual:** pelo botão **Run workflow**.
- **O que faz:** roda `scripts/verificar_producao.py`, que chama o endereço do site, guardado na **variável** `URL_PRODUCAO` do GitHub (não é segredo; padrão `https://professor-nta.up.railway.app`).
- **Paciência:** tenta por até 3 minutos, porque o deploy pode estar terminando.
- **Se falhar:** o job fica vermelho, e o Summary explica como voltar a versão anterior no Railway (*Deployments → ⋯ → Rollback*).

**Configuração feita uma vez, fora do repositório:**

| Passo | Quem | Onde |
|---|---|---|
| Criar o projeto `professor-nta` e o serviço ligado ao repositório, branch `main` | Eu, pelo conector do Railway (com a sua autorização) | — |
| Cadastrar as *Variables*: as 3 chaves de IA, `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` | **Você** (as chaves não passam por mim) | Railway → serviço → *Variables* |
| Ligar **Wait for CI** | Você (eu guio) | Railway → *Settings → Source* |
| Gerar o domínio `professor-nta.up.railway.app` | Eu, pelo conector, ou você em *Settings → Networking* | — |
| Criar a variável `URL_PRODUCAO` | Você | GitHub → *Settings → Secrets and variables → Actions → Variables* |
| Pausar o Space | Você, depois do aceite | Hugging Face → Space → *Settings → Pause* |

**Rollback:**
- **Código:** *Deployments → versão anterior → Rollback* no Railway.
- **Base:** a `producao` só muda quando um commit passa no portão. Para voltar o índice, reverta o commit do documento; o pipeline reindexa e promove de novo.

---

## 11. Critérios de aceite

- [ ] Abro `https://professor-nta.up.railway.app` e vejo a interface com a minha logo e as minhas cores, no computador e no celular (360 px), sem rolagem lateral.
- [ ] Alterno entre modo claro e escuro. A escolha fica salva ao recarregar a página.
- [ ] A tela inicial mostra as sugestões. Clico numa e a resposta chega **aos poucos**.
- [ ] A resposta sobre o material tem **cartões de fonte**. Ao clicar, vejo o trecho usado.
- [ ] Pergunta fora do material: aparece *"Não encontrei isso no material do curso."*, sem cartões.
- [ ] "Oi, tudo bem?" recebe resposta normal, sem cartões.
- [ ] Coloco um PDF com texto em `documentos/` com uma pergunta de teste sobre ele, faço commit, e o assistente passa a responder sobre o PDF, com o cartão mostrando o nome do PDF.
- [ ] Coloco um PDF escaneado: o portão para com a mensagem de PDF sem texto, e o site continua como estava.
- [ ] Abro o código-fonte da página e os arquivos JS no navegador e não encontro chave, prompt de sistema nem nome de modelo.
- [ ] Mando perguntas seguidas: na 11ª dentro de um minuto, aparece "Muitas perguntas seguidas. Tente de novo em N segundos", e o botão volta sozinho depois.
- [ ] Descomento as perguntas impossíveis: o `avaliar` fica vermelho, o Railway **não** publica (aparece como pulado/aguardando CI) e o site no ar continua funcionando.
- [ ] Depois de um deploy, o job **verificar-producao** fica verde e mostra a versão do commit.
- [ ] Desligo o servidor (ou corto a rede) e a interface mostra o erro com **Tentar de novo**, sem perder a pergunta.
- [ ] No Railway, *Deployments* mostra o histórico, e consigo fazer **rollback** para a versão anterior.
- [ ] O Space do Hugging Face está pausado.
- [ ] Todos os testes das Partes 1 e 2 continuam passando, com os ajustes da seção 9.2.

---

## 12. Ordem das tarefas (uma de cada vez)

| # | Tarefa | Entrega | Como você testa |
|---|---|---|---|
| **1** | **Servidor FastAPI** | `agente/servidor.py` e `limites.py`; roteador em eventos; bloco `servidor` no config; T26, T27 e T15/T16 novos | Rodar o servidor no computador e chamar as rotas com `curl` (eu passo os comandos) |
| **2** | **PDF na base** | `agente/pdf.py`, T19 ampliado, T29, a apostila em `documentos/`, 6 perguntas novas, `requirements-indice.txt`; avaliação real pelo botão manual | Ver os trechos do PDF com `mostrar_trechos.py`; relatório do avaliar com o PDF |
| **3** | **Interface: estrutura e estados** | Projeto Vite/React/TS/Tailwind; componentes; todos os estados com a API simulada; T28 | `npm run dev` e ver cada estado |
| **4** | **Interface: visual e acabamento** | Cores e logo do config, tema escuro, celular, Markdown, cartões de fonte, acessibilidade; ligada à API de verdade | Conversar no computador, de ponta a ponta, com o banco real |
| **5** | **Imagem Docker e `railway.json`** | `Dockerfile`, `.dockerignore`, `railway.json`; T30 e T31 | O job `imagem` verde; eu mostro os comandos para rodar a imagem no computador |
| **6** | **Pipeline** | Jobs `interface`, `imagem` e `promover`; sai o envio ao Space; `verificar.yml` com T32; sai o Gradio (`app.py`, `interface.py`, `publicar.py`); README novo | Botão manual numa branch: tudo verde, sem promover |
| **7** | **Railway no ar** | Projeto e serviço pelo conector; você cadastra as *Variables* e liga o Wait for CI; domínio; levamos para a `main` (com a sua permissão) | Abrir o endereço; verificar-producao verde |
| **8** | **Aceite e desligar o Space** | `ACEITE-parte3.md` com os roteiros da seção 11; você pausa o Space | Marcar cada item |

> Entre as tarefas 1 e 6, nada vai para a `main`: o Space continua no ar com a Parte 2 até o Railway estar pronto e aprovado (tarefa 7).

---

## 13. Erros comuns e como resolver

| Sintoma | Causa provável | Conserto |
|---|---|---|
| Railway publicou sem passar no portão | **Wait for CI** desligado | Ligar em *Settings → Source* |
| Railway usa "Python" em vez do Dockerfile | Commit sem `Dockerfile`/`railway.json`, ou branch errada | Conferir a branch em *Settings → Source* |
| Deploy falha no health check | `/api/saude` responde 503 | Ver o log do Railway; conferir `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` nas *Variables* |
| Health check estoura o tempo | O modelo não estava na imagem e está sendo baixado ao iniciar | Conferir o passo de download do modelo no `Dockerfile` (log do build) |
| Serviço no ar, mas sem endereço | Domínio não gerado | *Settings → Networking → Generate Domain* |
| Serviço reiniciando com `Out of memory` | Plano com pouca memória para o modelo | Plano Hobby; ver *Metrics → Memory* |
| Página em branco | `dist` ausente na imagem ou `base` errada no Vite | Ver o job `imagem` (T30); `base: "/"` no `vite.config.ts` |
| Erro de rede só no computador | API local fora do ar ou proxy do Vite errado | Subir o servidor na porta 8000 antes do `npm run dev` |
| Chave no JavaScript publicado | Variável `VITE_` com segredo | Remover, **revogar a chave** no provedor e manter só no servidor |
| `❌ … parece ser um PDF escaneado` | PDF só com imagens | Usar um PDF com texto selecionável (OCR fica fora) |
| Hit rate caiu depois de um PDF novo | Conversão ruim (títulos não reconhecidos, tabelas quebradas) | Ver os trechos com `mostrar_trechos.py --filtro`; ajustar o PDF de origem ou converter manualmente para `.md` |
| Muitos 429 numa sala de aula | Todos atrás do mesmo IP da rede | Aumentar `servidor.perguntas_por_minuto` no `config.yaml` |
| verificar-producao vermelho com "versão diferente" | O Railway ainda está trocando a versão, ou o deploy falhou | Esperar e rodar de novo pelo botão; se persistir, ver *Deployments* e fazer rollback |
| verificar-producao não rodou depois do deploy | O Railway não enviou o evento ao GitHub | Rodar pelo botão **Run workflow** do `verificar.yml` |
