"""Testes do portão T9–T14: troca automática, mensagens e proteção das chaves.

Nenhum teste chama uma IA de verdade: os provedores aqui são simulados.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from agente.config import Config, Provedor
from agente.roteador import MSG_SEM_CHAVE, montar_mensagens, responder

CHAVE_FALSA = "sk-" + "ant-" + "api03-" + "segredo" * 5


class ErroHttp(Exception):
    """Imita as exceções dos SDKs (que têm status_code e message)."""

    def __init__(self, status_code: int, message: str = "erro"):
        self.status_code, self.message = status_code, message
        super().__init__(message)


class APITimeoutError(Exception):
    """Mesmo nome da exceção de tempo esgotado dos SDKs."""


@dataclass
class ProvedorFalso:
    nome: str
    modelo: str = "modelo-x"
    chave: str = "chave-qualquer-123"
    pedacos: list[str] = field(default_factory=list)
    erro_antes: Exception | None = None
    erro_depois: Exception | None = None  # levantado após enviar os pedaços
    chamadas: int = 0
    ultimo_pedido: object = None

    def gerar(self, pedido):
        self.chamadas += 1
        self.ultimo_pedido = pedido
        if self.erro_antes:
            raise self.erro_antes
        yield from self.pedacos
        if self.erro_depois:
            raise self.erro_depois


@pytest.fixture
def config() -> Config:
    return Config(
        nome="Professor",
        descricao="d",
        cor_principal="#000000",
        cor_secundaria="#000000",
        logo=Path("assets/logo.png"),
        logo_altura=80,
        provedores=[Provedor("openrouter", "a"), Provedor("anthropic", "b"), Provedor("openai", "c")],
        max_tokens=1024,
        temperatura=0.5,
        tempo_limite_segundos=30,
        max_caracteres_pergunta=100,
        max_mensagens_historico=4,
        instrucoes="Você é um professor.",
    )


def final(gerador) -> str:
    """Última versão do texto acumulado (o que o usuário vê no fim)."""
    saidas = list(gerador)
    return saidas[-1] if saidas else ""


# ----------------------------------------------------------- caminho feliz


def test_primeiro_provedor_responde_em_streaming(config):
    p1 = ProvedorFalso("OpenRouter", pedacos=["Olá", ", ", "aluno!"])
    p2 = ProvedorFalso("Anthropic", pedacos=["não deveria"])
    saidas = list(responder("Oi", [], config, [p1, p2]))
    assert saidas == ["Olá", "Olá, ", "Olá, aluno!"]  # texto acumulado, palavra por palavra
    assert p2.chamadas == 0


def test_pedido_leva_instrucoes_e_parametros(config):
    p = ProvedorFalso("OpenAI", pedacos=["ok"])
    final(responder("Oi", [], config, [p]))
    assert p.ultimo_pedido.instrucoes == "Você é um professor."
    assert p.ultimo_pedido.max_tokens == 1024
    assert p.ultimo_pedido.temperatura == 0.5
    assert p.ultimo_pedido.mensagens == [{"role": "user", "content": "Oi"}]


# ------------------------------------------------- T9: troca automática


@pytest.mark.parametrize(
    "erro",
    [
        ErroHttp(429, "rate limit"),
        ErroHttp(402, "payment required"),
        ErroHttp(401, "invalid key"),
        ErroHttp(404, "model not found"),
        ErroHttp(503, "unavailable"),
        APITimeoutError("timeout"),
        ConnectionError("sem rede"),
    ],
)
def test_t9_primeiro_falha_antes_segundo_responde(erro, config):
    p1 = ProvedorFalso("OpenRouter", erro_antes=erro)
    p2 = ProvedorFalso("Anthropic", pedacos=["Resposta ", "do segundo"])
    assert final(responder("Oi", [], config, [p1, p2])) == "Resposta do segundo"
    assert p1.chamadas == 1 and p2.chamadas == 1


def test_t9_pula_ate_o_terceiro(config):
    p1 = ProvedorFalso("OpenRouter", erro_antes=ErroHttp(429))
    p2 = ProvedorFalso("Anthropic", erro_antes=ErroHttp(500))
    p3 = ProvedorFalso("OpenAI", pedacos=["terceiro"])
    assert final(responder("Oi", [], config, [p1, p2, p3])) == "terceiro"


def test_t9_resposta_vazia_tambem_troca(config):
    p1 = ProvedorFalso("OpenRouter", pedacos=["", ""])
    p2 = ProvedorFalso("Anthropic", pedacos=["ok"])
    assert final(responder("Oi", [], config, [p1, p2])) == "ok"


# ------------------------------------------- T10: falha depois de começar


def test_t10_falha_no_meio_mantem_texto_e_nao_troca(config):
    p1 = ProvedorFalso("OpenRouter", pedacos=["Começo da ", "resposta"], erro_depois=ErroHttp(502))
    p2 = ProvedorFalso("Anthropic", pedacos=["não deveria"])
    texto = final(responder("Oi", [], config, [p1, p2]))
    assert texto.startswith("Começo da resposta")
    assert "⚠️ A resposta foi interrompida" in texto
    assert "(502)" in texto
    assert p2.chamadas == 0


# ------------------------------------------------ T11: todos falharam


def test_t11_todos_falham_mostra_motivo_de_cada_um(config):
    provedores = [
        ProvedorFalso("OpenRouter", "google/gemma-4-31b-it:free", erro_antes=ErroHttp(429)),
        ProvedorFalso("Anthropic", "claude-haiku-4-5", erro_antes=ErroHttp(400, "Your credit balance is too low")),
        ProvedorFalso("OpenAI", "gpt-5-mini", erro_antes=ErroHttp(404)),
    ]
    texto = final(responder("Oi", [], config, provedores))
    assert texto.startswith("😕 Não consegui responder agora. Motivos:")
    assert "• OpenRouter (google/gemma-4-31b-it:free): limite de uso atingido; tente mais tarde (429)." in texto
    assert "• Anthropic (claude-haiku-4-5): sem crédito na conta (400)." in texto
    assert "• OpenAI (gpt-5-mini): modelo não encontrado: confira o ID no config.yaml (404)." in texto


@pytest.mark.parametrize(
    "erro,esperado",
    [
        (ErroHttp(401), "chave inválida ou revogada (401)"),
        (ErroHttp(403), "chave sem permissão para este modelo (403)"),
        (ErroHttp(402), "sem crédito na conta (402)"),
        (ErroHttp(429), "limite de uso atingido"),
        (ErroHttp(529, "Overloaded"), "provedor sobrecarregado (529)"),
        (ErroHttp(500), "provedor fora do ar ou instável (500)"),
        (ErroHttp(400, "bad"), "o provedor recusou o pedido (400)"),
        (APITimeoutError(), "demorou demais para responder (mais de 30 s)"),
        (ConnectionError(), "não foi possível conectar"),
        (ValueError("x"), "erro inesperado (ValueError)"),
    ],
)
def test_t11_motivos_em_portugues(erro, esperado, config):
    texto = final(responder("Oi", [], config, [ProvedorFalso("OpenAI", erro_antes=erro)]))
    assert esperado in texto


# ------------------------------------- T12: só quem tem chave / sem chave


def test_t12_sem_nenhum_provedor_mostra_como_cadastrar(config):
    assert list(responder("Oi", [], config, [])) == [MSG_SEM_CHAVE]
    assert "OPENROUTER_API_KEY" in MSG_SEM_CHAVE and "secrets do Space" in MSG_SEM_CHAVE


# (a montagem da fila a partir das chaves é testada em test_provedores.py)


# --------------------------------------------- T13: limite da pergunta


def test_t13_pergunta_longa_nao_chama_api(config):
    p = ProvedorFalso("OpenAI", pedacos=["x"])
    texto = final(responder("a" * 101, [], config, [p]))
    assert "tem 101 caracteres e o limite é 100" in texto
    assert p.chamadas == 0


def test_t13_pergunta_no_limite_passa(config):
    p = ProvedorFalso("OpenAI", pedacos=["ok"])
    assert final(responder("a" * 100, [], config, [p])) == "ok"


@pytest.mark.parametrize("pergunta", ["", "   ", None])
def test_pergunta_vazia_e_ignorada(pergunta, config):
    p = ProvedorFalso("OpenAI", pedacos=["x"])
    assert list(responder(pergunta, [], config, [p])) == []
    assert p.chamadas == 0


# ------------------------------------ T14: chave nunca aparece em lugar nenhum


def test_t14_chave_no_erro_nao_aparece_no_chat_nem_no_log(config, caplog):
    erro = ErroHttp(401, f"Invalid API key: {CHAVE_FALSA}")
    erro_estranho = RuntimeError(f"falhou com a chave {CHAVE_FALSA}")
    provedores = [
        ProvedorFalso("Anthropic", chave=CHAVE_FALSA, erro_antes=erro),
        ProvedorFalso("OpenAI", chave="outra-chave-sem-formato-123", erro_antes=erro_estranho),
    ]
    with caplog.at_level(logging.DEBUG, logger="agente"):
        saidas = list(responder("Oi", [], config, provedores))
    tudo = "\n".join(saidas) + "\n" + caplog.text
    assert CHAVE_FALSA not in tudo
    assert "outra-chave-sem-formato-123" not in tudo
    assert "Anthropic" in caplog.text  # o log registra quem falhou...


def test_t14_log_nao_guarda_a_pergunta(config, caplog):
    p = ProvedorFalso("OpenAI", pedacos=["ok"])
    with caplog.at_level(logging.DEBUG, logger="agente"):
        final(responder("minha pergunta secreta", [], config, [p]))
    assert "minha pergunta secreta" not in caplog.text
    assert "Resposta enviada por OpenAI" in caplog.text


# --------------------------------------------------------------- histórico


def test_historico_limitado_e_comeca_pelo_usuario():
    historico = [
        {"role": "user", "content": "p1"},
        {"role": "assistant", "content": "r1"},
        {"role": "user", "content": "p2"},
        {"role": "assistant", "content": "r2"},
        {"role": "user", "content": "p3"},
        {"role": "assistant", "content": "r3"},
    ]
    # limite 3: sobrariam [r2, p3, r3]; a primeira precisa ser do usuário, então r2 sai
    assert montar_mensagens(historico, "p4", 3) == [
        {"role": "user", "content": "p3"},
        {"role": "assistant", "content": "r3"},
        {"role": "user", "content": "p4"},
    ]


def test_historico_zero_envia_so_a_pergunta():
    historico = [{"role": "user", "content": "p1"}, {"role": "assistant", "content": "r1"}]
    assert montar_mensagens(historico, "p2", 0) == [{"role": "user", "content": "p2"}]


def test_historico_aceita_formatos_do_gradio_e_ignora_lixo():
    historico = [
        {"role": "user", "content": [{"type": "text", "text": "parte 1"}, {"type": "text", "text": "parte 2"}]},
        {"role": "assistant", "content": {"text": "resposta"}},
        {"role": "system", "content": "ignorar"},
        {"role": "user", "content": ""},
        "lixo",
    ]
    assert montar_mensagens(historico, "nova", 10) == [
        {"role": "user", "content": "parte 1\nparte 2"},
        {"role": "assistant", "content": "resposta"},
        {"role": "user", "content": "nova"},
    ]


def test_config_substituivel(config):
    """Garante que a fixture é imutável (dataclass frozen) e pode ser variada com replace."""
    outra = replace(config, max_caracteres_pergunta=5)
    assert "limite é 5" in final(responder("123456", [], outra, [ProvedorFalso("X")]))
