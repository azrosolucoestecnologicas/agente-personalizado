"""Tela do chat (Gradio): cabeçalho, cores, exemplos e textos em português.

Tudo o que é personalizável vem do config.yaml. Este arquivo só "desenha".
"""

from __future__ import annotations

import base64
import html
import mimetypes
from collections.abc import Iterator, Sequence
from pathlib import Path

import gradio as gr

from agente.config import Config
from agente.provedores import Provedor
from agente.roteador import responder

# Textos fixos da tela (tudo em português).
TEXTO_PLACEHOLDER = "Digite sua dúvida e pressione Enter…"
TEXTO_ENVIAR = "Enviar"
TEXTO_PARAR = "Parar"
TEXTO_VAZIO = "### 👋 Olá!\nFaça uma pergunta ou clique em um dos exemplos abaixo."
MAX_CONVERSAS_SIMULTANEAS = 10  # RF20: protege contra sobrecarga e gasto excessivo

# RF6: os botões internos do Gradio (Limpar, Tentar novamente...) seguem o idioma
# do navegador. Estas traduções fazem que apareçam em português em qualquer idioma.
# Idiomas que o Gradio traduz sozinho (em todos eles, forçamos o português).
IDIOMAS_DO_GRADIO = (
    "en ar ca de es et eu fa fr he hi id it ja ko lt nb nl pl pt pt-BR ro ru sv ta th tr uk ur uz vi zh-CN zh-TW"
).split()
TEXTOS_INTERNOS_PT = {
    "chatbot.clear": "Limpar conversa",
    "chatbot.retry": "Tentar novamente",
    "chatbot.undo": "Desfazer",
    "chatbot.edit": "Editar",
    "chatbot.submit": "Enviar",
    "chatbot.cancel": "Cancelar",
    "chatbot.like": "Gostei",
    "chatbot.dislike": "Não gostei",
    "common.copy": "Copiar",
    "common.clear": "Limpar",
    "common.submit": "Enviar",
    "common.stop": "Parar",
    "common.error": "Erro",
    "common.loading": "Carregando",
}

TEXTO_ESCURO = "#111827"
TEXTO_CLARO = "#FFFFFF"


# ------------------------------------------------------------------- cores


def _rgb(cor: str) -> tuple[int, int, int]:
    """'#0F2540' ou '#FFF' -> (15, 37, 64)."""
    cor = cor.lstrip("#")
    if len(cor) == 3:
        cor = "".join(c * 2 for c in cor)
    return int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16)


def _luminancia(cor: str) -> float:
    """Luminância relativa (padrão WCAG): 0 = preto, 1 = branco."""

    def canal(valor: int) -> float:
        c = valor / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(v) for v in _rgb(cor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(cor_a: str, cor_b: str) -> float:
    """Razão de contraste WCAG (1 a 21). Texto normal legível: 4.5 ou mais."""
    claro, escuro = sorted((_luminancia(cor_a), _luminancia(cor_b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def cor_do_texto(*fundos: str) -> str:
    """RF5: branco ou quase-preto, o que tiver MAIS contraste com o pior dos fundos."""
    pior_branco = min(contraste(TEXTO_CLARO, f) for f in fundos)
    pior_escuro = min(contraste(TEXTO_ESCURO, f) for f in fundos)
    return TEXTO_CLARO if pior_branco >= pior_escuro else TEXTO_ESCURO


# --------------------------------------------------------------- cabeçalho


def logo_em_data_uri(caminho: Path) -> str:
    """Embute a logo na página (dispensa configurar pastas públicas no Gradio)."""
    tipo = mimetypes.guess_type(caminho.name)[0] or "image/png"
    if caminho.suffix.lower() == ".svg":
        tipo = "image/svg+xml"
    dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
    return f"data:{tipo};base64,{dados}"


def montar_cabecalho(config: Config) -> str:
    nome = html.escape(config.nome)
    descricao = html.escape(config.descricao)
    return f"""
<header class="cabecalho">
  <img class="cabecalho-logo" src="{logo_em_data_uri(config.logo)}" alt="Logo de {nome}"
       style="height:{config.logo_altura}px">
  <div>
    <h1 class="cabecalho-nome">{nome}</h1>
    <p class="cabecalho-descricao">{descricao}</p>
  </div>
</header>
"""


def montar_css(config: Config) -> str:
    """RF4: fundo com as cores do config; cartão do chat sempre claro e legível."""
    texto = cor_do_texto(config.cor_principal, config.cor_secundaria)
    return f"""
body, gradio-app, .gradio-container, .main, .app {{
  background: linear-gradient(160deg, {config.cor_principal} 0%, {config.cor_secundaria} 100%) fixed !important;
}}
footer {{ opacity: .75; }}
footer, footer * {{ color: {texto} !important; }}
.gradio-container {{ max-width: 920px !important; margin: 0 auto !important; }}
.cabecalho {{
  display: flex; align-items: center; gap: 18px; padding: 20px 8px 12px;
  color: {texto};
}}
.cabecalho-logo {{ width: auto; max-width: 40vw; object-fit: contain; flex-shrink: 0; }}
.cabecalho-nome {{ margin: 0; font-size: 1.9rem; line-height: 1.2; color: {texto} !important; }}
.cabecalho-descricao {{ margin: 6px 0 0; font-size: 1.05rem; opacity: .92; color: {texto} !important; }}
@media (max-width: 600px) {{
  .cabecalho {{ flex-direction: column; text-align: center; }}
  .cabecalho-nome {{ font-size: 1.5rem; }}
}}

/* Cartão do chat: sempre claro, mesmo no modo escuro do navegador. */
.cartao-chat, .dark .cartao-chat {{
  --body-background-fill: #FFFFFF;
  --background-fill-primary: #FFFFFF;
  --background-fill-secondary: #F3F4F6;
  --block-background-fill: #FFFFFF;
  --input-background-fill: #FFFFFF;
  --body-text-color: {TEXTO_ESCURO};
  --body-text-color-subdued: #4B5563;
  --block-label-text-color: #4B5563;
  --input-placeholder-color: #6B7280;
  --border-color-primary: #E5E7EB;
  --color-accent-soft: #EEF2FF;
  --chatbot-text-size: 1rem;
  background: #FFFFFF !important;
  color: {TEXTO_ESCURO};
  border-radius: 16px !important;
  padding: 12px !important;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .25);
}}
.cartao-chat .message-row .user, .cartao-chat .user .message-bubble-border {{
  background: {config.cor_principal} !important;
  border-color: {config.cor_principal} !important;
}}
.cartao-chat .user, .cartao-chat .user * {{ color: {cor_do_texto(config.cor_principal)} !important; }}
.cartao-chat {{ width: 100% !important; }}

/* Perguntas de exemplo: botões visíveis, com a cor principal ao passar o mouse. */
.cartao-chat button.example {{
  background: #F3F4F6 !important;
  border: 1px solid #E5E7EB !important;
  border-radius: 12px !important;
  transition: border-color .15s, background .15s;
}}
.cartao-chat button.example:hover {{
  background: #FFFFFF !important;
  border-color: {config.cor_principal} !important;
}}
.cartao-chat button.example * {{ color: {TEXTO_ESCURO} !important; }}

/* Botões Enviar/Parar com a cor principal. */
.cartao-chat button.submit-button, .cartao-chat button.stop-button {{
  background: {config.cor_principal} !important;
  color: {cor_do_texto(config.cor_principal)} !important;
  border-radius: 999px !important;
  padding: 6px 18px !important;
}}
.cartao-chat .input-container {{
  border: 1px solid #D1D5DB; border-radius: 14px; padding: 4px 6px;
}}
"""


def tema(config: Config) -> gr.themes.Base:
    texto_botao = cor_do_texto(config.cor_principal)
    return gr.themes.Soft().set(
        button_primary_background_fill=config.cor_principal,
        button_primary_background_fill_hover=config.cor_secundaria,
        button_primary_text_color=texto_botao,
        button_primary_border_color=config.cor_principal,
    )


# ---------------------------------------------------------------- app


def criar_app(config: Config, provedores: Sequence[Provedor]) -> tuple[gr.Blocks, dict]:
    """Monta a tela. Devolve o app e as opções para o `launch()`."""

    def conversar(mensagem: str, historico: list[dict]) -> Iterator[str]:
        yield from responder(mensagem, historico, config, provedores)

    with gr.Blocks(title=config.nome) as app:
        gr.HTML(montar_cabecalho(config))
        with gr.Column(elem_classes="cartao-chat"):
            chat = gr.ChatInterface(
                fn=conversar,
                chatbot=gr.Chatbot(
                    placeholder=TEXTO_VAZIO,
                    show_label=False,
                    buttons=["copy"],
                    height="60vh",
                ),
                textbox=gr.Textbox(
                    placeholder=TEXTO_PLACEHOLDER,
                    show_label=False,
                    max_length=config.max_caracteres_pergunta,
                    autofocus=True,
                    submit_btn=TEXTO_ENVIAR,
                    stop_btn=TEXTO_PARAR,  # aparece só enquanto a IA responde
                ),
                examples=config.exemplos or None,
                run_examples_on_click=True,
                cache_examples=False,  # nunca chamar a IA na inicialização
                concurrency_limit=MAX_CONVERSAS_SIMULTANEAS,
                api_visibility="private",  # só pela tela, não por chamadas diretas à API
                autofocus=True,
            )

    app.chat = chat  # referência usada nos testes
    app.queue(default_concurrency_limit=MAX_CONVERSAS_SIMULTANEAS)
    opcoes_launch = {
        "theme": tema(config),
        "css": montar_css(config),
        "favicon_path": str(config.logo) if config.logo.suffix.lower() != ".svg" else None,
        "footer_links": [],
        "i18n": gr.I18n(
            **{idioma: TEXTOS_INTERNOS_PT for idioma in IDIOMAS_DO_GRADIO}
        ),  # sem links técnicos em inglês no rodapé
        "head": '<meta name="description" content="' + html.escape(config.descricao) + '">',
    }
    return app, opcoes_launch
