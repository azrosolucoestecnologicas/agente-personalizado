"""Teste do portão T15: o app monta a tela sem chaves e sem rede.

Também confere cores/contraste (RF4, RF5), textos em português (RF6),
exemplos (RF7) e a recusa de subir com config inválido (RF1).
"""

from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import gradio as gr
import pytest

from agente.config import carregar_config
from agente.interface import (
    TEXTO_ENVIAR,
    TEXTO_PARAR,
    TEXTO_PLACEHOLDER,
    TEXTOS_INTERNOS_PT,
    contraste,
    cor_do_texto,
    criar_app,
    montar_cabecalho,
    montar_css,
)

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def config():
    return carregar_config()


def _componentes(app: gr.Blocks, tipo):
    return [b for b in app.blocks.values() if isinstance(b, tipo)]


def _chat(app: gr.Blocks) -> gr.ChatInterface:
    return app.chat


# ------------------------------------------------------ T15: teste de fumaça


def test_t15_app_py_importa_sem_chaves_e_sem_rede(monkeypatch):
    for variavel in (
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
    ):
        monkeypatch.delenv(variavel, raising=False)
    sys.modules.pop("app", None)
    app = importlib.import_module("app")  # importar NÃO chama launch() nem baixa o modelo
    assert isinstance(app.demo, gr.Blocks)
    assert app.provedores == []
    assert app.rag is not None and "SUPABASE_URL" in app.rag.motivo_indisponivel  # Parte 2: sem secrets, sem rede
    assert callable(app.exigencia_zerogpu)  # RF21: função @spaces.GPU presente
    assert "theme" in app.opcoes_launch and "css" in app.opcoes_launch


def test_t15_sem_chave_o_chat_explica_como_cadastrar(config):
    app, _ = criar_app(config, [])
    respostas = list(_chat(app).fn("Oi", []))
    assert "Nenhuma chave de IA configurada" in respostas[-1]


def test_t15_chat_liga_no_roteador(config):
    class Falso:
        nome, modelo, chave = "OpenRouter", "m", "k"

        def gerar(self, pedido):
            yield from ["Olá ", "aluno"]

    app, _ = criar_app(config, [Falso()])
    assert list(_chat(app).fn("Oi", [])) == ["Olá ", "Olá aluno"]


def test_rf1_config_invalido_impede_o_app_de_subir(tmp_path):
    for item in ("app.py", "agente", "assets"):
        origem = RAIZ / item
        (shutil.copytree if origem.is_dir() else shutil.copy)(origem, tmp_path / item)
    texto = re.sub(
        r'cor_principal: "#[0-9A-Fa-f]+"', 'cor_principal: "#12345G"', (RAIZ / "config.yaml").read_text("utf-8")
    )
    (tmp_path / "config.yaml").write_text(texto, encoding="utf-8")
    assert "#12345G" in texto
    resultado = subprocess.run([sys.executable, "app.py"], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert resultado.returncode == 1
    assert "#12345G" in resultado.stderr


# --------------------------------------------------- tela e português (RF6)


def test_rf6_textos_da_tela_em_portugues(config):
    app, opcoes = criar_app(config, [])
    caixa = next(t for t in _componentes(app, gr.Textbox) if t.placeholder == TEXTO_PLACEHOLDER)
    assert caixa.submit_btn == TEXTO_ENVIAR
    assert app.chat.original_stop_btn == TEXTO_PARAR  # o Gradio só mostra durante a resposta
    assert caixa.max_length == config.max_caracteres_pergunta
    chatbot = _componentes(app, gr.Chatbot)[0]
    assert "Olá" in chatbot.placeholder
    assert opcoes["footer_links"] == []  # sem links em inglês no rodapé
    traducoes = opcoes["i18n"].translations_dict
    assert traducoes["en"]["chatbot.clear"] == "Limpar conversa"
    assert traducoes["en"] == TEXTOS_INTERNOS_PT


def test_rf7_exemplos_viram_botoes_sem_chamar_ia_na_inicializacao(config):
    chat = _chat(criar_app(config, [])[0])
    assert [e[0] if isinstance(e, list) else e for e in chat.examples] == config.exemplos
    assert chat.run_examples_on_click is True
    assert chat.cache_examples is False


def test_sem_exemplos_nao_quebra(config):
    chat = _chat(criar_app(replace(config, exemplos=[]), [])[0])
    assert not chat.examples


def test_api_direta_desligada(config):
    assert _chat(criar_app(config, [])[0]).api_visibility == "private"


# ------------------------------------------------ cabeçalho e cores (RF3-5)


def test_rf3_cabecalho_tem_logo_nome_e_descricao(config):
    cabecalho = montar_cabecalho(config)
    tipo = "svg+xml" if config.logo.suffix == ".svg" else config.logo.suffix.lstrip(".")
    assert f"data:image/{tipo};base64," in cabecalho
    assert f"height:{config.logo_altura}px" in cabecalho
    assert "Professor de Dados &amp; IA" in cabecalho  # '&' escapado
    assert config.descricao in cabecalho


def test_rf3_cabecalho_escapa_html(config):
    perigoso = replace(config, nome="<script>alert(1)</script>", descricao='"><img src=x>')
    cabecalho = montar_cabecalho(perigoso)
    assert "<script>" not in cabecalho and "<img src=x>" not in cabecalho


def test_rf4_css_usa_as_cores_do_config(config):
    css = montar_css(replace(config, cor_principal="#112233", cor_secundaria="#445566"))
    assert "#112233 0%" in css and "#445566 100%" in css


@pytest.mark.parametrize(
    "fundo,esperado",
    [
        ("#0F2540", "#FFFFFF"),
        ("#000", "#FFFFFF"),
        ("#FFFFFF", "#111827"),
        ("#FFD700", "#111827"),
        ("#F5EFE4", "#111827"),
    ],
)
def test_rf5_cor_do_texto_por_contraste(fundo, esperado):
    assert cor_do_texto(fundo) == esperado


@pytest.mark.parametrize("fundos", [("#0F2540", "#1E4D7A"), ("#0F2540", "#FFFFFF"), ("#FFD700", "#FF8C00")])
def test_rf5_degrade_usa_o_pior_caso(fundos):
    # Escolhe o texto cujo PIOR contraste entre as duas cores do degradê é o maior possível.
    escolhida = cor_do_texto(*fundos)
    outra = "#111827" if escolhida == "#FFFFFF" else "#FFFFFF"
    assert min(contraste(escolhida, f) for f in fundos) >= min(contraste(outra, f) for f in fundos)


def test_contraste_padrao_wcag():
    assert round(contraste("#000000", "#FFFFFF"), 1) == 21.0
    assert contraste("#FFFFFF", "#FFFFFF") == 1.0
    assert contraste("#FFF", "#FFFFFF") == 1.0  # formato curto


def test_cor_destaque_nos_botoes_e_no_filete(config):
    css = montar_css(replace(config, cor_principal="#132A5C", cor_secundaria="#27488F", cor_destaque="#E0262B"))
    assert "border-bottom: 3px solid #E0262B" in css
    assert "background: #E0262B !important" in css  # Enviar/Parar
    assert "border-color: #E0262B !important" in css  # exemplo ao passar o mouse


def test_sem_cor_destaque_usa_a_principal(config):
    css = montar_css(replace(config, cor_principal="#112233", cor_destaque=""))
    assert "border-bottom: 3px solid #112233" in css


def test_descricao_em_prata_sobre_fundo_escuro_e_legivel(config):
    css = montar_css(replace(config, cor_principal="#132A5C", cor_secundaria="#27488F"))
    assert "color: #D9DDE2 !important" in css
    assert min(contraste("#D9DDE2", "#132A5C"), contraste("#D9DDE2", "#27488F")) >= 4.5


def test_descricao_escura_sobre_fundo_claro(config):
    css = montar_css(replace(config, cor_principal="#FFFFFF", cor_secundaria="#F5F5F5"))
    assert "#D9DDE2" not in css
