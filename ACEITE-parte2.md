# Teste de aceite — Parte 2 (RAG)

Roteiro para percorrer os critérios de aceite da spec da Parte 2 (seção 10). Marque cada item depois de testar.

- **Chat:** https://huggingface.co/spaces/thiagoazro/agente-personalizado
- **Execuções do GitHub Actions:** aba **Actions** → "Testar e publicar" → jobs `testes`, `avaliar` e `publicar`
- **Relatório da busca (hit rate, MRR, o que veio em cada pergunta):** execução → aba **Summary**, bloco "T25"
- **Banco:** Supabase → projeto `agente-personalizado` → **Table Editor** → tabela `trechos`
- **Log do Space:** aba **Logs**, linhas `Base de conhecimento: N trechos na produção` e `Busca: ...`

> **Tempo de cada publicação:** depois de salvar na `main`, o site muda em cerca de 5 minutos
> (1 min de testes + 1 a 2 min de indexação e avaliação + 1 a 2 min de build).

## Antes do primeiro deploy (tarefa 8)

| Onde | Nome | O que é | Situação |
|---|---|---|---|
| GitHub → Settings → Secrets and variables → **Actions** | `SUPABASE_URL` | `https://oriybunpthtgcdptpzmw.supabase.co` | ✅ cadastrado (o job avaliar já usou) |
| GitHub → Settings → Secrets and variables → **Actions** | `SUPABASE_SECRET_KEY` | chave `sb_secret_…` (Supabase → Project Settings → API Keys) | ✅ cadastrado (o job avaliar já usou) |
| Space → Settings → Variables and secrets → **New secret** | `SUPABASE_URL` | o mesmo endereço acima | ⏳ você |
| Space → Settings → Variables and secrets → **New secret** | `SUPABASE_PUBLISHABLE_KEY` | chave `sb_publishable_…` (Supabase → Project Settings → API Keys) | ⏳ você |
| Space | `SUPABASE_SECRET_KEY` | **NUNCA** no Space: a conferência barra a publicação | — |

Depois de cadastrar, aperte **Run workflow** em qualquer branch que não seja a `main`: o job
**conferir configuração** mostra ✅ `Supabase no Space: SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY (só leitura)`.

## Situação

| # | Critério | Situação |
|---|---|---|
| 1 | No Table Editor, vejo os trechos das duas apostilas em `teste` e `producao`, com fonte, seção e vetor | ⏳ depois do 1º deploy (`teste` ✅ já indexada pelo avaliar) |
| 2 | O log do Space mostra `Base de conhecimento: N trechos na produção` | ⏳ você (✅ teste T23) |
| 3 | Pergunta sobre as apostilas: a resposta termina com **"Fontes consultadas"** certas | ⏳ você (roteiro A) |
| 4 | Pergunta fora do material: responde exatamente *"Não encontrei isso no material do curso."* | ⏳ você (roteiro A) |
| 5 | Pergunta com outras palavras ainda acha o trecho certo | ⏳ você (roteiro A) |
| 6 | "Oi, tudo bem?" e "como você funciona?" recebem resposta normal | ⏳ você (✅ teste T23) |
| 7 | Perguntas impossíveis: **avaliar** vermelho, **publicar** não roda, `producao` igual | ⏳ você (roteiro B) |
| 8 | `peso_palavras: 0` mostra no relatório qual pergunta muda | ⏳ você (roteiro C) |
| 9 | A chave secreta não está no Space; a conferência acusa se alguém a cadastrar | ⏳ você (roteiro D; ✅ teste) |
| 10 | Com a chave publicável, a coleção `teste` não aparece e gravar é negado | ✅ verificado no banco (tarefa 4) |
| 11 | Todos os testes da Parte 1 (T1 a T17) continuam passando | ✅ job `testes` verde |

## Roteiros

Todas as edições são feitas **pelo site do GitHub**, na branch `main`: abra o arquivo → lápis (Edit) →
altere → **Commit changes**. Depois de cada teste, **desfaça a alteração** do mesmo jeito.

### A — Conversa com a base (itens 3, 4, 5 e 6)
1. "Oi, tudo bem?" → resposta curta de boas-vindas, sem fontes.
2. "O que é CI/CD?" → resposta com **Fontes consultadas:** `parte1-cicd-deploy.md › 06 CI/CD…`.
3. "Como juntar o resultado da busca por palavras com o da busca por significado?" (sem a palavra
   RRF) → fonte `parte2-rag.md › 12 Recuperação híbrida e RRF`.
4. "Qual a capital da Austrália?" → exatamente *"Não encontrei isso no material do curso."*, sem fontes.
5. Nos **Logs**, cada pergunta mostra `Busca: N trecho(s), M acima de 0.83`.

### B — Portão barra a publicação (item 7)
No `perguntas_teste.yaml`, descomente as **quatro** perguntas impossíveis (tire o `# ` do começo
das linhas, mantendo os 2 espaços de recuo). O hit rate cai abaixo de 0,80: o job **avaliar** fica
vermelho, o **publicar** aparece como *skipped*, a `producao` continua com os mesmos trechos e o chat
responde como antes. Comente as quatro de novo e salve: tudo volta a ficar verde.

### C — Peso da busca por palavras (item 8)
No `config.yaml`, mude `peso_palavras: 0.3` para `peso_palavras: 0`. No **Summary** do avaliar, a
coluna "Palavras / Sentido" mostra `—` na busca por palavras e a posição de algumas perguntas muda.
Volte para `0.3`.

### D — Chave secreta no Space (item 9)
Cadastre no Space um secret chamado `SUPABASE_SECRET_KEY` com qualquer texto (ex.: `teste`), **não a
chave de verdade**. Aperte **Run workflow** numa branch que não seja a `main`: o job **conferir
configuração** fica vermelho com "SUPABASE_SECRET_KEY está cadastrada no Space… fica SÓ no GitHub".
Apague o secret do Space.

## O que já foi verificado

- **Permissões do banco (tarefa 4):**
  - com o papel `anon`, ler a `producao` funciona;
  - gravar dá *permission denied*;
  - `promover_teste()` dá *permission denied for function*;
  - `buscar_hibrido(..., p_colecao => 'teste')` devolve 0 linhas.
- **Calibração (tarefa 5):** com o `e5-base` e `peso_palavras: 0.3`, o hit rate@3 das 12 perguntas foi
  0,83. A `similaridade_minima: 0.83` separa os trechos certos (≥ 0,836) das perguntas fora do material
  (≤ 0,830).
- **Chaves:** a varredura do T8/T22 roda em todo push; nenhuma chave do Supabase no repositório nem no
  histórico.
