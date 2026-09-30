# Teste de aceite — Parte 1

Roteiro para percorrer os critérios de aceite da spec (seção 8). Marque cada item depois de testar.

- **Chat:** https://huggingface.co/spaces/thiagoazro/agente-personalizado
- **Execuções do GitHub Actions:** aba **Actions** do repositório → "Testar e publicar"
- **Onde ver qual IA respondeu:** no Space, aba **Logs**, linhas `Resposta enviada por ...` e `... falhou antes de responder: ...`

> **Tempo de cada publicação:** depois de salvar na `main`, o site muda em cerca de 3 minutos
> (1 min de testes + 1 a 2 min de build). Acompanhe pela aba Actions.

## Situação

| # | Critério | Situação |
|---|---|---|
| 1 | Abro o link e vejo logo, nome, descrição e as cores no fundo | ⏳ você |
| 2 | Todos os textos da tela estão em português | ⏳ você (✅ verificado localmente em navegadores pt, en e fr) |
| 3 | Clico num exemplo e recebo resposta didática, palavra por palavra | ⏳ você |
| 4 | Funciona com só uma das três chaves (cada uma) | ⏳ você (roteiro A) |
| 5 | Se o 1º provedor falha, o próximo responde sozinho | ⏳ você (roteiro B) |
| 6 | Se todos falham, aparece o motivo de cada um, sem chave | ⏳ você (roteiro C) |
| 7 | Sem nenhuma chave, a página abre e explica o que cadastrar | ✅ verificado localmente e pelo teste T12 (opcional no site: exige apagar os secrets) |
| 8 | Pergunta muito longa recebe aviso e não gasta crédito | ⏳ você (✅ teste T13) |
| 9 | Mudo uma cor ou um exemplo pelo GitHub e o site muda sozinho | ⏳ você (roteiro D) |
| 10 | Erro de propósito no config: publicação barrada, site antigo no ar | ⏳ você (roteiro E) |
| 11 | Texto com formato de chave num arquivo: publicação bloqueada | ⏳ você (roteiro F) |
| 12 | Nenhuma chave no repositório, no histórico do Git ou nos logs do Actions | ✅ verificado (detalhes no fim) |

## Roteiros

Todas as edições são feitas **pelo site do GitHub**, na branch `main`: abra o arquivo → lápis (Edit) →
altere → **Commit changes**. Depois de cada teste, **desfaça a alteração** do mesmo jeito.

### Itens 1, 2, 3 e 8 — uso normal
1. Abra o chat. A primeira visita do dia pode levar 1 a 2 minutos (o Space "acorda").
2. Confira o topo e as cores; confira que botões e avisos estão em português.
3. Clique em um exemplo; depois faça uma pergunta de continuação ("e o que é ETL?").
4. Cole na caixa um texto com mais de 2000 caracteres: a caixa não aceita passar do limite.

### A — Uma chave só (item 4)
Deixar só um provedor na lista tem o mesmo efeito de ter só a chave dele, sem mexer nos secrets.
No `config.yaml`, em `ia.provedores`, deixe **só** o bloco da Anthropic:
```yaml
  provedores:
    - nome: anthropic
      modelo: "claude-haiku-4-5"
```
Publique, faça uma pergunta e veja nos Logs `Resposta enviada por Anthropic`. Repita só com
`openai` e só com `openrouter`. No fim, volte a lista original com os três.

### B — Troca automática (item 5)
Troque o modelo do OpenRouter por um que não existe: `modelo: "modelo/que-nao-existe"`.
Pergunte algo: a resposta vem normalmente, e os Logs mostram
`OpenRouter (...) falhou antes de responder: modelo não encontrado ... Tentando o próximo.`
seguido de `Resposta enviada por Anthropic`.

### C — Todos falham (item 6)
Troque os **três** modelos por nomes inexistentes. Pergunte algo: o chat mostra
"😕 Não consegui responder agora. Motivos:" com uma linha por provedor, sem nenhuma chave.

### D — Atualização automática (item 9)
Troque `cor_principal` por `"#7B1FA2"` (roxo) e um dos `exemplos`. Em ~3 minutos, recarregue o
chat (Ctrl+F5): fundo roxo e o exemplo novo.

### E — Erro barrado, site antigo no ar (item 10)
Troque `cor_principal` por `"#12345G"`. Resultado esperado:
- Actions: execução **vermelha**; o job "publicar" nem começa;
- Summary: `❌ aparencia.cor_principal: "#12345G" não é uma cor válida...`;
- o chat continua funcionando com as cores anteriores.

### F — Chave no código bloqueada (item 11)
Faça este teste numa **branch separada**, para a chave falsa não ficar no histórico da `main`
(o portão de testes é o mesmo em qualquer branch):
1. No GitHub, abra o seletor de branches, digite `teste-chave` e clique em **Create branch**.
2. Nessa branch, crie o arquivo `teste-chave.txt` contendo uma chave **falsa**: digite
   `sk-ant-api03-` e, colado logo depois, 40 letras `x` (tudo numa linha só, sem espaços).
   O texto não aparece inteiro aqui justamente porque a varredura bloquearia este documento.
3. Resultado esperado: a execução fica **vermelha** nos passos "T8: procurar chaves" e o Summary
   mostra `teste-chave.txt:1: chave da Anthropic encontrada (sk-ant…(oculto))`. Na `main`, isso
   impediria a publicação. Se o *Push protection* do GitHub estiver ligado, ele pode bloquear o
   commit antes: também vale.
4. Apague a branch `teste-chave` (aba **Branches** → lixeira).

## Item 12 — o que foi verificado

- **Arquivos atuais:** `python scripts/procurar_chaves.py` → nenhuma chave.
- **Histórico do Git (todas as branches):** `python scripts/procurar_chaves.py --historico` → nenhuma
  chave de verdade. A única ocorrência era uma chave inventada (o alfabeto em ordem) num teste
  antigo, registrada como falsa conhecida só pela impressão digital SHA-256. Essa verificação
  agora roda em toda execução do Actions.
- **Logs do Actions:** revisados os logs das execuções com credenciais (conferência e primeira
  publicação): o `HF_TOKEN` aparece só como `***`, e não há nenhum texto com formato de chave.
