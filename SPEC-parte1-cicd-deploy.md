# SPEC — Parte 1: assistente de IA no ar com CI/CD

> **Status:** rascunho, aguardando aprovação
> **Projeto:** `agente-personalizado`
> **Repositório GitHub:** `azrosolucoestecnologicas/agente-personalizado`
> **Space no Hugging Face:** `thiagoazro/agente-personalizado`
> **Origem:** `IDEIA-parte1.md`

Esta spec descreve **o que** será construído e **como saberemos que ficou certo**. O código só é escrito depois que ela for aprovada, uma tarefa por vez (seção 9).

---

## Glossário rápido (para iniciantes)

| Termo | O que significa aqui |
|---|---|
| **Provedor** | Empresa que fornece a IA: OpenRouter, Anthropic ou OpenAI. |
| **Chave de API** | Senha que o app usa para falar com o provedor. Nunca vai para o código. |
| **Secret** | Lugar protegido (no Hugging Face ou no GitHub) onde a chave fica guardada. |
| **Space** | O "site" gratuito do Hugging Face onde o chat fica publicado. |
| **Gradio** | Biblioteca Python que desenha a tela de chat. |
| **GitHub Actions** | Robô do GitHub que roda os testes e publica o site a cada alteração. |
| **Portão de testes** | Conjunto de verificações que precisa passar antes de publicar. Se falhar, nada é publicado. |
| **Streaming** | A resposta aparece aos poucos, palavra por palavra. |
| **Token** | Pedaço de texto (cerca de ¾ de uma palavra) usado para medir o tamanho das respostas. |
| **Troca automática (fallback)** | Se um provedor falhar, o app tenta o próximo da lista sozinho. |

---

## 1. Objetivo, público e escopo

### 1.1 Objetivo
Publicar na internet um chat com IA, com um link público, que responde dúvidas de **engenharia de dados e Inteligência Artificial** de forma didática, como um professor. Tudo o que é personalizável fica em **um único arquivo** (`config.yaml`), editável pelo site do GitHub. Cada alteração salva na branch `main` é testada e, se estiver certa, publicada automaticamente.

### 1.2 Público
- **Quem usa o chat:** alunos de engenharia de dados e IA, sem login.
- **Quem mantém o projeto:** o dono do repositório (iniciante em programação), que edita só o `config.yaml` e as chaves nos secrets.

### 1.3 O que entra na Parte 1
- Chat em Gradio com streaming, em português.
- Três provedores de IA (OpenRouter, Anthropic, OpenAI), usados na ordem escolhida e com troca automática.
- Arquivo de configuração único com validação.
- Portão de testes (configuração, segredos e lógica) no GitHub Actions.
- Deploy automático no Hugging Face Spaces a cada push na `main`.
- Bloqueio de publicação se alguma chave aparecer no código.

### 1.4 O que fica para depois
| Fica para | Item |
|---|---|
| **Parte 2** | Base de conhecimento com os seus documentos (RAG: busca nos documentos antes de responder). |
| **Parte 3** | Site próprio, com domínio próprio e visual feito do zero. |
| **Fora do escopo** | Login de usuários, conversas salvas, painel de administração, cobrança, métricas de uso. |

---

## 2. Stack escolhida e restrições do Hugging Face Spaces

### 2.1 Stack

| Camada | Escolha | Por quê |
|---|---|---|
| Linguagem | **Python 3.12** (confirmado: a ZeroGPU aceita 3.12.12 e 3.10.13) | Padrão do Hugging Face e do Gradio. |
| Interface | **Gradio** (`gr.Blocks` + `gr.ChatInterface`), versão fixada | Pedido seu; é o SDK nativo dos Spaces e o único aceito pela ZeroGPU. |
| Configuração | **YAML** (`config.yaml`) lido com `PyYAML` | Fácil de ler e editar pelo site do GitHub. |
| IA: Anthropic | SDK oficial **`anthropic`** | Requisito. |
| IA: OpenAI | SDK **`openai`** | Requisito. |
| IA: OpenRouter | SDK **`openai`** com `base_url="https://openrouter.ai/api/v1"` | Requisito; o OpenRouter segue o formato da OpenAI. |
| ZeroGPU | Pacote **`spaces`** | Exigido pelo hardware ZeroGPU (ver 2.3). |
| Testes | **pytest** + **ruff** (verificador de estilo) | Simples e padrão de mercado. |
| CI/CD | **GitHub Actions** + **`huggingface_hub`** (envio dos arquivos) | Gratuito e integrado ao GitHub. |

### 2.2 Provedores de IA e troca automática

Configuração inicial:

| Ordem | Provedor | Variável de ambiente (secret) | Modelo inicial |
|---|---|---|---|
| 1º | OpenRouter | `OPENROUTER_API_KEY` | `google/gemma-4-31b-it:free` |
| 2º | Anthropic | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` |
| 3º | OpenAI | `OPENAI_API_KEY` | `gpt-5-mini` (*confirme o nome no painel da OpenAI; troca-se no `config.yaml`*) |

Tamanho máximo da resposta: **1024 tokens**.

Regras:
1. Basta **uma** chave. As outras são opcionais.
2. O app monta a **fila de provedores** assim: segue a ordem do `config.yaml` e mantém só quem tem chave cadastrada.
3. Se um provedor falhar **antes da primeira palavra** (limite de uso, sem crédito, chave inválida, modelo inexistente, fora do ar, demora demais), o app tenta o próximo.
4. Se falhar **depois** de começar a responder, o app **não** troca de provedor, porque a resposta ficaria duplicada. Ele avisa no chat que a resposta foi interrompida.
5. Se todos falharem, o chat mostra **o motivo de cada um**, em português.

### 2.3 Restrições conhecidas do Hugging Face Spaces

| Restrição | Impacto no projeto |
|---|---|
| **ZeroGPU exige conta PRO** (ou organização Enterprise) para hospedar o Space. | Sem PRO, não é possível escolher ZeroGPU. Alternativa: "CPU basic" (grátis). O código funciona igual nos dois. |
| **ZeroGPU só aceita SDK Gradio.** | Compatível com a escolha do Gradio. |
| **ZeroGPU exige ao menos uma função marcada com `@spaces.GPU`**, senão o Space pode falhar ao iniciar. | O app terá uma função mínima com `@spaces.GPU`. As chamadas às APIs de IA rodam **fora** da GPU, então não gastam a sua cota de GPU. |
| **Observação honesta:** nesta Parte 1 o app não usa GPU, porque toda a IA roda nos provedores externos. | A ZeroGPU só fará diferença na Parte 2, se você rodar modelos de embeddings no próprio Space. |
| **O hardware é escolhido à mão** nas configurações do Space, não pelo código. | Passo manual na seção 7. |
| O Space precisa de um `README.md` com um **cabeçalho YAML** (sdk, versão, arquivo principal). | O `README.md` do repositório terá esse cabeçalho. |
| **Se o build no Hugging Face falhar, o Space fica fora do ar.** A versão antiga não continua rodando. | Por isso o portão de testes no GitHub precisa pegar os erros **antes** de enviar qualquer arquivo. |
| O Space **"dorme"** depois de um tempo sem visitas. | A primeira visita depois disso demora de 1 a 2 minutos para abrir. |
| Arquivos grandes (> 10 MB) precisam de Git LFS. | A logo deve ter até 1 MB (validado). |
| Secrets do Space viram **variáveis de ambiente** para o app. | O app lê `os.environ["OPENROUTER_API_KEY"]` etc. |
| O disco do Space é temporário. | Não há conversas salvas (já está fora do escopo). |
| O link é público: qualquer pessoa pode gastar seus créditos. | Limite de tamanho da pergunta, limite de histórico, modelo gratuito primeiro e fila com concorrência limitada. |

---

## 3. Estrutura de arquivos do projeto

```
agente-personalizado/
├── README.md                    # Capa do Space (cabeçalho YAML) + instruções
├── config.yaml                  # ⭐ O ÚNICO arquivo que você edita no dia a dia
├── app.py                       # Ponto de entrada: monta a tela e inicia o Gradio
├── requirements.txt             # Bibliotecas do app, com versões fixas
├── requirements-dev.txt         # Bibliotecas só para testes (pytest, ruff)
├── pyproject.toml               # Configuração do pytest e do ruff
├── .gitignore                   # Impede subir .env, caches etc.
├── assets/
│   └── logo.png                 # Logo (provisória até você enviar a sua)
├── agente/                      # Código do app, separado por responsabilidade
│   ├── __init__.py
│   ├── config.py                # Lê e valida o config.yaml
│   ├── provedores.py            # Um "adaptador" por provedor (OpenRouter, Anthropic, OpenAI)
│   ├── roteador.py              # Fila de provedores + troca automática + mensagens de erro
│   ├── erros.py                 # Traduz erros técnicos para português, sem vazar chaves
│   └── interface.py             # Cabeçalho, cores, CSS, textos em português
├── scripts/
│   ├── validar_config.py        # Valida o config.yaml e explica os erros em português
│   ├── procurar_chaves.py       # Procura chaves de API esquecidas no código
│   └── publicar.py              # Envia os arquivos para o Space (usado pelo Actions)
├── tests/
│   ├── test_config.py
│   ├── test_segredos.py
│   ├── test_roteador.py
│   ├── test_app.py
│   └── test_readme.py
├── .github/
│   └── workflows/
│       └── deploy.yml           # Portão de testes + publicação
├── IDEIA-parte1.md
└── SPEC-parte1-cicd-deploy.md   # Este documento
```

**Vai para o Space:** `README.md`, `app.py`, `config.yaml`, `requirements.txt`, `assets/` e `agente/`.
**Fica só no GitHub:** `tests/`, `scripts/`, `.github/`, `requirements-dev.txt`, `pyproject.toml` e os arquivos `.md` de ideia e spec.

---

## 4. Contrato do arquivo de configuração (`config.yaml`)

### 4.1 Exemplo completo (valores iniciais)

```yaml
# ============================================================
#  CONFIGURAÇÃO DO ASSISTENTE: edite só este arquivo
#  Depois de salvar na branch main, o site se atualiza sozinho.
# ============================================================

assistente:
  nome: "Professor de Dados & IA"
  descricao: "Tire suas dúvidas de Engenharia de Dados e Inteligência Artificial."

aparencia:
  cor_principal: "#0F2540"      # cor do topo do degradê
  cor_secundaria: "#1E4D7A"     # opcional: cor do fim do degradê
  logo: "assets/logo.png"
  logo_altura: 80               # em pixels

ia:
  provedores:                   # ordem de preferência: o 1º é tentado primeiro
    - nome: openrouter
      modelo: "google/gemma-4-31b-it:free"
    - nome: anthropic
      modelo: "claude-haiku-4-5"
    - nome: openai
      modelo: "gpt-5-mini"
  max_tokens: 1024
  temperatura: 0.5
  tempo_limite_segundos: 30
  max_caracteres_pergunta: 2000
  max_mensagens_historico: 10

comportamento:
  instrucoes: |
    Você é um professor paciente e didático de Engenharia de Dados e IA.
    Fala com alunos iniciantes e intermediários, sempre em português do Brasil.
    Explique com exemplos simples e, quando útil, passo a passo.
    Não responda assuntos fora de dados e IA; recuse com educação.
    Não invente fatos: se não souber, diga que não sabe.

exemplos:
  - "O que é um pipeline de dados?"
  - "Qual a diferença entre data lake e data warehouse?"
  - "Como funciona um modelo de linguagem?"
  - "O que é ETL e ELT?"
```

> Nome, cores e logo acima são **provisórios** (você ainda não os definiu). Troque quando quiser; o portão de testes confere tudo.

### 4.2 Tabela de campos

| Campo | Obrigatório? | Valores aceitos | Padrão |
|---|---|---|---|
| `assistente.nome` | **Sim** | Texto de 1 a 60 caracteres | — |
| `assistente.descricao` | **Sim** | Texto de 1 a 200 caracteres | — |
| `aparencia.cor_principal` | **Sim** | Cor hexadecimal `#RRGGBB` ou `#RGB` (ex.: `#0F2540`) | — |
| `aparencia.cor_secundaria` | Não | Cor hexadecimal, como acima | Igual à `cor_principal` (fundo liso, sem degradê) |
| `aparencia.logo` | **Sim** | Caminho de um arquivo **existente** dentro de `assets/`, com extensão `.png`, `.jpg`, `.jpeg`, `.svg` ou `.webp`, até 1 MB | — |
| `aparencia.logo_altura` | Não | Número inteiro de 24 a 300 (pixels) | `80` |
| `ia.provedores` | **Sim** | Lista com 1 a 3 itens; a ordem da lista é a ordem de preferência | — |
| `ia.provedores[].nome` | **Sim** | `openrouter`, `anthropic` ou `openai` (minúsculas, sem repetir) | — |
| `ia.provedores[].modelo` | **Sim** | Texto não vazio (ID do modelo no provedor) | — |
| `ia.max_tokens` | Não | Inteiro de 64 a 8192 | `1024` |
| `ia.temperatura` | Não | Número de 0.0 a 1.0 (mais alto = mais criativo) | `0.5` |
| `ia.tempo_limite_segundos` | Não | Inteiro de 5 a 120: quanto esperar pela primeira palavra antes de desistir do provedor | `30` |
| `ia.max_caracteres_pergunta` | Não | Inteiro de 100 a 8000 | `2000` |
| `ia.max_mensagens_historico` | Não | Inteiro de 0 a 50: quantas mensagens anteriores enviar à IA (controla o custo) | `10` |
| `comportamento.instrucoes` | **Sim** | Texto de 20 a 8000 caracteres (as "instruções de sistema") | — |
| `exemplos` | Não | Lista de 0 a 6 textos, cada um com 1 a 150 caracteres | `[]` (nenhum botão) |

### 4.3 Regras gerais do contrato
- **Campos desconhecidos são erro.** Assim um erro de digitação como `cor_principall` não passa em silêncio. A mensagem sugere o nome correto ("você quis dizer `cor_principal`?").
- **As chaves de API nunca entram no `config.yaml`.** Qualquer campo com cara de chave é recusado.
- Um provedor listado **sem** chave nos secrets é simplesmente pulado. Isso não é erro.
- Uma chave cadastrada de um provedor **que não está** na lista é ignorada.
- Mensagens de erro sempre dizem **qual campo**, **o que está errado** e **como corrigir**, com o número da linha quando possível.

---

## 5. Requisitos funcionais

### Configuração
- **RF1.** Ao iniciar, o app lê o `config.yaml` e o valida pelas regras da seção 4. Se estiver inválido, o app não inicia e mostra a lista de erros em português.
- **RF2.** O validador pode ser rodado sozinho (`python scripts/validar_config.py`) e retorna código de saída ≠ 0 quando há erro, para uso no GitHub Actions.

### Aparência
- **RF3.** O topo da página mostra a logo (na altura configurada), o nome e a descrição do assistente.
- **RF4.** O fundo da página usa a `cor_principal`, em degradê até a `cor_secundaria` quando esta existir. A área do chat tem fundo claro e texto escuro, para boa leitura em qualquer combinação de cores.
- **RF5.** A cor do texto do cabeçalho (branco ou preto) é escolhida automaticamente pelo contraste com a cor de fundo.
- **RF6.** Todos os textos visíveis ficam em português: placeholder da caixa de texto, botões (enviar, parar, limpar), avisos e mensagens de erro.
- **RF7.** Os `exemplos` aparecem como botões clicáveis. Clicar envia aquela pergunta.

### Provedores e troca automática
- **RF8.** O app lê as chaves só das variáveis de ambiente `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` e `OPENAI_API_KEY`.
- **RF9.** A fila de provedores segue a ordem de `ia.provedores` e inclui só quem tem chave não vazia.
- **RF10.** O Anthropic usa o SDK `anthropic`. OpenAI e OpenRouter usam o SDK `openai`; no OpenRouter, com `base_url="https://openrouter.ai/api/v1"` e os cabeçalhos opcionais de identificação do app (nome do assistente).
- **RF11.** As respostas chegam em streaming, palavra por palavra.
- **RF12.** Se um provedor falhar antes do primeiro pedaço de texto, o app tenta o próximo da fila sem que o usuário precise fazer nada. Contam como falha: chave inválida (401/403), sem crédito (402), limite de uso (429), modelo inexistente (404), erro do servidor (5xx), falha de conexão e tempo limite estourado.
- **RF13.** Se um provedor falhar depois de já ter começado a responder, o app mantém o texto recebido e acrescenta: "⚠️ A resposta foi interrompida (motivo). Tente novamente." Ele não troca de provedor.
- **RF14.** Se todos os provedores falharem, o chat mostra uma mensagem com uma linha por provedor, por exemplo:
  > Não consegui responder agora. Motivos:
  > • OpenRouter (google/gemma-4-31b-it:free): limite de uso atingido (429).
  > • Anthropic (claude-haiku-4-5): sem crédito na conta (400/402).
- **RF15.** Se nenhuma chave estiver cadastrada, a página abre normalmente e o chat responde: "Nenhuma chave de IA configurada. Cadastre OPENROUTER_API_KEY, ANTHROPIC_API_KEY ou OPENAI_API_KEY nos secrets do Space."
- **RF16.** Nenhuma mensagem de erro, no chat ou no log, contém o valor de uma chave. Os erros passam por uma limpeza antes de aparecer.
- **RF17.** `max_tokens`, `temperatura` e `instrucoes` são aplicados igualmente aos três provedores.

### Conversa e proteção de custo
- **RF18.** As `instrucoes` são enviadas como mensagem de sistema. O histórico enviado à IA é limitado a `max_mensagens_historico`.
- **RF19.** Perguntas vazias são ignoradas. Perguntas acima de `max_caracteres_pergunta` recebem um aviso amigável e **nenhuma** API é chamada.
- **RF20.** A fila do Gradio limita as conversas simultâneas (padrão: 10), para evitar sobrecarga e gasto excessivo.

### Plataforma
- **RF21.** O app tem uma função mínima com `@spaces.GPU` para atender a exigência da ZeroGPU. As chamadas de IA não passam por ela. Fora da ZeroGPU (no seu computador ou no CI), o decorador não faz nada.
- **RF22.** O log do Space registra qual provedor respondeu e quais falharam, com o motivo. O log **não** registra o texto das perguntas nem as chaves.

---

## 6. Portão de testes

Tudo roda no GitHub Actions **sem chaves reais e sem internet para os provedores**; as IAs são simuladas nos testes. Se qualquer item falhar, **a publicação não acontece** e o site antigo continua no ar.

| # | Verificação | O que pega |
|---|---|---|
| **T1** | O `config.yaml` existe e é um YAML válido | Aspas ou indentação erradas (mostra a linha). |
| **T2** | Todos os campos obrigatórios estão presentes e não vazios | "Esqueci o nome", "apaguei as instruções". |
| **T3** | Tipos e faixas de valores (números, tamanhos de texto, listas) | `max_tokens: mil`, `temperatura: 3`. |
| **T4** | Cores são hexadecimais válidas | `#12345G`, `azul-claro`, `0F2540` sem `#`. |
| **T5** | A logo existe em `assets/`, tem extensão aceita e até 1 MB | Logo com nome diferente, arquivo esquecido, imagem pesada. |
| **T6** | Provedores: nomes válidos, sem repetição, modelo preenchido | `open-ai`, `anthropic` duas vezes, modelo vazio. |
| **T7** | Nenhum campo desconhecido (com sugestão do nome certo) | Erros de digitação em nomes de campo. |
| **T8** | **Varredura de chaves:** nenhum arquivo do repositório contém algo com formato de chave (`sk-or-…`, `sk-ant-…`, `sk-proj-…`, `sk-…` longas, `hf_…`), e não há arquivos `.env` versionados | Chave colada no código por engano. |
| **T9** | Troca automática: o 1º falha antes de responder → o 2º responde | RF12. |
| **T10** | Falha depois de começar → mantém o texto, avisa e **não** troca | RF13. |
| **T11** | Todos falham → a mensagem lista cada provedor e o motivo em português | RF14. |
| **T12** | Só entram na fila provedores com chave; sem nenhuma chave → mensagem amigável | RF9 e RF15. |
| **T13** | Pergunta longa demais é recusada **sem** chamar a API | RF19. |
| **T14** | Mensagens de erro e logs nunca contêm o valor da chave (teste com chave falsa) | RF16 e RF22. |
| **T15** | Teste de fumaça: o app monta a tela sem chaves e sem rede, sem erro | Erros de importação ou de sintaxe que derrubariam o Space. |
| **T16** | O cabeçalho do `README.md` está correto: `sdk: gradio`, `app_file: app.py` existe e `sdk_version` é igual à versão do Gradio no `requirements.txt` | Build quebrado no Hugging Face. |
| **T17** | `ruff` sem erros | Código com erros óbvios. |

Quando o portão falhar, o GitHub Actions escreve no **resumo da execução** (aba *Actions* → execução → *Summary*) a lista de problemas em português, por exemplo:

> ❌ `aparencia.cor_principal`: "#12345G" não é uma cor válida. Use o formato #RRGGBB, por exemplo "#0F2540".

---

## 7. Pipeline de deploy com GitHub Actions

### 7.1 Como funciona

```
Você salva uma alteração no GitHub
          │
          ▼
┌──────────────────────────┐
│ Job 1: "testes"          │  roda em QUALQUER branch e em pull requests
│  • instala dependências  │
│  • T1–T7  validar config │
│  • T8     procurar chaves│
│  • T9–T17 pytest + ruff  │
└──────────┬───────────────┘
           │ passou? ── não ──► ❌ para aqui. Site antigo continua no ar.
           │ sim                   Resumo mostra o que corrigir.
           ▼
┌──────────────────────────┐
│ Job 2: "publicar"        │  só roda em push na branch main
│  • envia os arquivos do  │
│    app para o Space      │
│  • acompanha o build até │
│    o Space ficar RUNNING │
└──────────┬───────────────┘
           ▼
   ✅ Site atualizado em poucos minutos
```

Detalhes:
- **Arquivo:** `.github/workflows/deploy.yml`.
- **Gatilhos:** `push` em qualquer branch, `pull_request` e execução manual (`workflow_dispatch`).
- **Publicação:** `scripts/publicar.py` usa `huggingface_hub` para enviar só os arquivos do app (lista da seção 3) e apagar do Space os arquivos que não existem mais.
- **Acompanhamento:** depois do envio, o script consulta o estado do Space por até ~10 minutos. Se der `BUILD_ERROR` ou `RUNTIME_ERROR`, o job fica vermelho e mostra o link do log.
- **Uma publicação por vez:** `concurrency` evita que dois envios rodem juntos.
- **Segredo usado:** apenas `HF_TOKEN` (no GitHub). As chaves de IA **nunca** passam pelo GitHub.

### 7.2 O que você precisa configurar à mão (uma vez só)

**No Hugging Face**
1. Ter conta **PRO**, que é necessária para ZeroGPU. Sem PRO, use o hardware "CPU basic" no passo 3.
2. Criar o Space: *New Space* → dono `thiagoazro`, nome `agente-personalizado`, SDK **Gradio**, visibilidade **Public**.
3. Em *Settings → Space hardware*, escolher **ZeroGPU**.
4. Em *Settings → Variables and secrets*, clicar em **New secret** (secret, não "variable") e cadastrar as chaves que você tiver:
   - `OPENROUTER_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `OPENAI_API_KEY`
5. Criar um token de acesso: *Settings da conta → Access Tokens → Create new token* → tipo **Fine-grained**, com permissão de **escrita** só no Space `thiagoazro/agente-personalizado`. Copie o token (começa com `hf_`).

**No GitHub** (repositório `azrosolucoestecnologicas/agente-personalizado`)
6. *Settings → Secrets and variables → Actions → New repository secret* → nome `HF_TOKEN`, valor = token do passo 5.
7. Conferir se a branch padrão é `main` e se o GitHub Actions está habilitado (*Settings → Actions → General*).
8. **Recomendado:** *Settings → Code security* → ativar **Secret scanning** e **Push protection** (o GitHub bloqueia o push se detectar uma chave). Isso é uma segunda camada além do T8.
9. **Recomendado:** *Settings → Branches* → regra para `main` exigindo que o check **"testes"** passe antes de fazer merge.

---

## 8. Critérios de aceite

- [ ] Abro `https://huggingface.co/spaces/thiagoazro/agente-personalizado`, vejo logo, nome e descrição no topo e as cores configuradas no fundo.
- [ ] Todos os textos da tela estão em português.
- [ ] Clico em uma pergunta de exemplo e recebo uma resposta didática, aparecendo palavra por palavra.
- [ ] Com **só uma** das três chaves cadastrada (testar cada uma), o chat funciona.
- [ ] Com o 1º provedor falhando (ex.: modelo trocado para um nome inexistente), o chat responde pelo próximo sem eu fazer nada.
- [ ] Com todos falhando, o chat mostra o motivo de cada provedor, sem mostrar nenhuma chave.
- [ ] Sem nenhuma chave, a página abre e o chat explica quais secrets cadastrar.
- [ ] Uma pergunta muito longa recebe um aviso e não gasta crédito.
- [ ] Mudo uma cor ou um exemplo no `config.yaml` pelo site do GitHub, salvo na `main` e, minutos depois, o site mostra a mudança.
- [ ] Coloco de propósito uma cor inválida (`#12345G`): o Actions fica vermelho, o resumo diz o que corrigir e o site antigo continua funcionando.
- [ ] Colo de propósito um texto no formato de chave num arquivo: a publicação é bloqueada (T8).
- [ ] Nenhuma chave de IA aparece no repositório, no histórico do Git ou nos logs do Actions.

---

## 9. Ordem das tarefas de implementação (uma de cada vez)

Cada tarefa termina com **"como testar"** e só avançamos depois da sua confirmação.

| # | Tarefa | Entrega | Como você testa |
|---|---|---|---|
| **1** | **Base e configuração** | Estrutura de pastas, `.gitignore`, `config.yaml` inicial, logo provisória, `agente/config.py`, `scripts/validar_config.py`, testes T1–T7 | Rodar o validador, errar uma cor de propósito e ver a mensagem em português |
| **2** | **Varredura de chaves** | `scripts/procurar_chaves.py` + T8 | Criar um arquivo com uma chave falsa e ver o bloqueio |
| **3** | **Provedores e troca automática** | `agente/provedores.py`, `agente/roteador.py`, `agente/erros.py` + T9–T14 (com IAs simuladas) | Rodar `pytest` e ler os cenários de falha simulados |
| **4** | **Interface Gradio** | `agente/interface.py`, `app.py` (cabeçalho, cores, exemplos, português, limite de pergunta, `@spaces.GPU`) + T15 | Rodar o app no seu computador (ou no Codespaces) com uma chave e conversar |
| **5** | **Pacote do Space** | `README.md` com cabeçalho YAML, `requirements.txt` com versões fixas, `requirements-dev.txt` + T16–T17 | Conferir o README e rodar todos os testes |
| **6** | **Pipeline no GitHub Actions** | `.github/workflows/deploy.yml` + `scripts/publicar.py` | Fazer push numa branch e ver o job "testes" verde (sem publicar) |
| **7** | **Configuração manual e 1º deploy** | Você segue a seção 7.2; fazemos o merge na `main` | Ver o job "publicar" verde e abrir o link do Space |
| **8** | **Teste de aceite** | Percorrer o checklist da seção 8 | Marcar cada item |

---

## 10. Erros comuns e como resolver

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| Actions vermelho em "validar config" | Erro no `config.yaml` | Abra a execução → *Summary*. A mensagem diz o campo e o que corrigir. |
| "YAML inválido na linha N" | Indentação com TAB, aspas não fechadas, `:` dentro de texto sem aspas | Use 2 espaços (nunca TAB) e coloque textos com `:` ou `#` entre aspas. |
| "cor inválida" | Faltou o `#` ou há letra fora de 0–9/A–F | Use `"#0F2540"`, com aspas. |
| "logo não encontrada" | O nome no `config.yaml` é diferente do arquivo (maiúsculas contam!) | Envie a imagem para `assets/` e copie o nome exato. |
| Actions bloqueado em "procurar chaves" | Uma chave foi colada em algum arquivo | Apague a chave do arquivo **e revogue-a no provedor** (ela já ficou no histórico do Git). Cadastre uma nova só nos secrets do Space. |
| Job "publicar" falha com 401/403 | `HF_TOKEN` ausente, expirado ou sem permissão de escrita no Space | Gere um novo token *fine-grained* com escrita no Space e atualize o secret `HF_TOKEN` no GitHub. |
| Job "publicar" falha com 404 | O Space não existe ou o nome está diferente | Crie o Space `thiagoazro/agente-personalizado` (passo 7.2.2). |
| Space em "Build error" | Versão de biblioteca incompatível | Veja a aba *Logs* do Space. Normalmente é versão do Gradio/Python; o T16 existe para evitar isso. |
| Space em "Runtime error" citando `@spaces.GPU` | Hardware ZeroGPU sem função GPU | Não deve acontecer (RF21); se acontecer, avise na tarefa correspondente. |
| Não aparece a opção ZeroGPU | Conta sem PRO | Assine o PRO ou use "CPU basic" (o app funciona igual). |
| Chat: "Nenhuma chave de IA configurada" | Secrets não cadastrados, com nome errado ou cadastrados como *variable* | Cadastre como **secret** com o nome exato e reinicie o Space (*Settings → Restart*). |
| Chat: "OpenRouter: limite de uso atingido (429)" | Modelos `:free` têm limite diário e ficam lotados em horários de pico | Normal: o app passa para o próximo provedor. Para diminuir, coloque créditos no OpenRouter ou troque a ordem. |
| Chat: "sem crédito (402)" | Conta do provedor sem saldo | Adicione crédito ou remova o provedor da lista. |
| Chat: "modelo não encontrado (404)" | ID do modelo digitado errado ou modelo descontinuado | Confira o ID exato no site do provedor e corrija no `config.yaml`. |
| Mudei o `config.yaml` e o site não mudou | Salvou em outra branch, o Actions falhou ou o navegador está com cache | Confirme a branch `main`, veja a aba *Actions* e recarregue a página com Ctrl+F5. |
| Primeira visita muito lenta | O Space estava "dormindo" | Normal: espere 1 a 2 minutos. |
