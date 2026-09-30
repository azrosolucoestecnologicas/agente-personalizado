---
# Cabeçalho lido pelo Hugging Face Spaces. Não apague as linhas "---".
# Guia dos campos: https://huggingface.co/docs/hub/spaces-config-reference
title: "Professor de Dados & IA"
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "6.28.0"   # precisa ser igual à versão do gradio no requirements.txt
python_version: "3.12"  # versão aceita pela ZeroGPU
app_file: app.py
short_description: "Tira-dúvidas de Engenharia de Dados e IA"
pinned: false
---

# 🎓 Professor de Dados & IA

Chat com inteligência artificial que tira dúvidas de **Engenharia de Dados e IA**
de forma didática, como um professor. Funciona com **OpenRouter**, **Anthropic** ou
**OpenAI**: basta ter uma das chaves. Se um provedor falhar, o app tenta o próximo sozinho.

- **Chat publicado:** https://huggingface.co/spaces/thiagoazro/agente-personalizado
- **Especificação completa:** [`SPEC-parte1-cicd-deploy.md`](SPEC-parte1-cicd-deploy.md)

---

## ✏️ Como personalizar (sem programar)

Tudo fica em **um único arquivo: [`config.yaml`](config.yaml)**. Pelo site do GitHub:

1. Abra o `config.yaml` e clique no **lápis** (Edit).
2. Altere o que quiser: nome, descrição, cores, logo, modelos de IA, instruções, exemplos.
3. Clique em **Commit changes** (na branch `main`).
4. Em poucos minutos o site se atualiza sozinho.

Se algo estiver errado (uma cor inválida, um campo vazio, uma logo que não existe),
**a publicação é barrada e o site antigo continua no ar**. Veja o motivo na aba
**Actions** do GitHub → execução em vermelho → **Summary**.

Para trocar a logo: envie a imagem para a pasta [`assets/`](assets) (PNG, JPG, SVG ou WEBP, até 1 MB)
e ajuste a linha `logo:` do `config.yaml`.

## 🔑 Chaves de IA (nunca no código!)

As chaves ficam **só** nos secrets do Space: **Settings → Variables and secrets → New secret**.

| Nome do secret | Provedor |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter (tem modelos gratuitos, terminados em `:free`) |
| `ANTHROPIC_API_KEY` | Anthropic (Claude) |
| `OPENAI_API_KEY` | OpenAI |

Cadastre pelo menos uma. A ordem de preferência e o modelo de cada provedor ficam no `config.yaml`.
Se alguém colocar uma chave no código por engano, a publicação é bloqueada.

## 💻 Rodar no seu computador (opcional)

Precisa de Python 3.12. No terminal, dentro da pasta do projeto:

```bash
pip install -r requirements-dev.txt          # instala tudo (app + testes)
export OPENROUTER_API_KEY="sua-chave"        # no Windows: set OPENROUTER_API_KEY=sua-chave
python app.py                                # abra http://127.0.0.1:7860
```

## ✅ Verificações (as mesmas que rodam antes de publicar)

```bash
python scripts/validar_config.py   # confere o config.yaml
python scripts/procurar_chaves.py  # procura chaves esquecidas no código
python -m pytest -q                # testes automáticos (não gastam crédito)
ruff check .                       # verificador de estilo do código
```

## 🗂️ Estrutura

| Caminho | O que é |
|---|---|
| `config.yaml` | ⭐ O único arquivo que você edita no dia a dia |
| `assets/` | Logo |
| `app.py` | Ponto de entrada do chat |
| `agente/` | Código do app (configuração, provedores, troca automática, tela) |
| `scripts/` | Validador, varredura de chaves e teste pelo terminal |
| `tests/` | Testes automáticos |
| `.github/workflows/` | Publicação automática (GitHub Actions) |
