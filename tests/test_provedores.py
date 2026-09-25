"""Testes dos adaptadores com os SDKs de verdade (anthropic e openai).

Em vez da internet, os SDKs falam com um servidor FALSO local que imita as
APIs da Anthropic e da OpenAI/OpenRouter. Nenhum crédito é gasto.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from agente.config import Config, Provedor
from agente.provedores import (
    Pedido,
    ProvedorAnthropic,
    ProvedorCompativelOpenAI,
    criar_provedores,
)
from agente.roteador import responder

PEDIDO = Pedido(
    instrucoes="Você é um professor.",
    mensagens=[{"role": "user", "content": "Oi"}],
    max_tokens=321,
    temperatura=0.5,
)


# ------------------------------------------------------------- servidor falso


class ServidorFalso:
    """Guarda as requisições recebidas e responde conforme `roteiro`.

    Cada item do roteiro é ("texto", ["pedaço", ...]) ou ("erro", status, mensagem).
    Um item é consumido por requisição; o último se repete.
    """

    def __init__(self):
        self.requisicoes: list[dict] = []
        self.roteiro: list[tuple] = []
        servidor = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silencia o log do http.server
                pass

            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                servidor.requisicoes.append(
                    {
                        "caminho": self.path,
                        "corpo": corpo,
                        "cabecalhos": {k.lower(): v for k, v in self.headers.items()},
                    }
                )
                passo = servidor.roteiro.pop(0) if len(servidor.roteiro) > 1 else servidor.roteiro[0]
                if passo[0] == "erro":
                    _, status, mensagem = passo
                    dados = json.dumps({"type": "error", "error": {"type": "api_error", "message": mensagem}})
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(dados)))
                    self.end_headers()
                    self.wfile.write(dados.encode())
                    return
                eventos = self._anthropic(passo[1]) if self.path.endswith("/messages") else self._openai(passo[1])
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for nome, dados in eventos:
                    linha = (f"event: {nome}\n" if nome else "") + f"data: {dados}\n\n"
                    self.wfile.write(linha.encode())
                    self.wfile.flush()

            @staticmethod
            def _anthropic(pedacos):
                msg = {
                    "id": "msg_1", "type": "message", "role": "assistant", "model": "m", "content": [],
                    "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 0},
                }  # fmt: skip
                yield "message_start", json.dumps({"type": "message_start", "message": msg})
                bloco = {"type": "text", "text": ""}
                yield (
                    "content_block_start",
                    json.dumps({"type": "content_block_start", "index": 0, "content_block": bloco}),
                )
                for p in pedacos:
                    delta = {"type": "text_delta", "text": p}
                    yield "content_block_delta", json.dumps({"type": "content_block_delta", "index": 0, "delta": delta})
                yield "content_block_stop", json.dumps({"type": "content_block_stop", "index": 0})
                fim = {"stop_reason": "end_turn", "stop_sequence": None}
                yield (
                    "message_delta",
                    json.dumps({"type": "message_delta", "delta": fim, "usage": {"output_tokens": 3}}),
                )
                yield "message_stop", json.dumps({"type": "message_stop"})

            @staticmethod
            def _openai(pedacos):
                for p in pedacos:
                    pedaco = {
                        "id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "m",
                        "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}],
                    }  # fmt: skip
                    yield None, json.dumps(pedaco)
                yield None, "[DONE]"

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._http.server_port}"
        threading.Thread(target=self._http.serve_forever, daemon=True).start()

    def fechar(self):
        self._http.shutdown()


@pytest.fixture
def servidor(monkeypatch):
    # Garante que a conexão local não passe por proxy.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    s = ServidorFalso()
    yield s
    s.fechar()


# ------------------------------------------------------------------ Anthropic


def test_anthropic_streaming_e_parametros(servidor):
    servidor.roteiro = [("texto", ["Olá", ", aluno"])]
    p = ProvedorAnthropic("claude-haiku-4-5", "chave-teste", 30, base_url=servidor.url)
    assert list(p.gerar(PEDIDO)) == ["Olá", ", aluno"]
    req = servidor.requisicoes[0]
    assert req["caminho"].endswith("/v1/messages")
    assert req["corpo"]["model"] == "claude-haiku-4-5"
    assert req["corpo"]["system"] == "Você é um professor."
    assert req["corpo"]["max_tokens"] == 321
    assert req["corpo"]["temperature"] == 0.5
    assert req["corpo"]["stream"] is True
    assert req["cabecalhos"]["x-api-key"] == "chave-teste"


def test_anthropic_tenta_sem_temperatura_quando_modelo_recusa(servidor):
    servidor.roteiro = [
        ("erro", 400, "temperature is not supported for this model"),
        ("texto", ["ok"]),
    ]
    p = ProvedorAnthropic("claude-sonnet-5", "k", 30, base_url=servidor.url)
    assert list(p.gerar(PEDIDO)) == ["ok"]
    assert "temperature" in servidor.requisicoes[0]["corpo"]
    assert "temperature" not in servidor.requisicoes[1]["corpo"]


def test_anthropic_erro_429_sobe_com_status(servidor):
    servidor.roteiro = [("erro", 429, "rate limited")]
    p = ProvedorAnthropic("claude-haiku-4-5", "k", 30, base_url=servidor.url)
    with pytest.raises(Exception) as erro:
        list(p.gerar(PEDIDO))
    assert erro.value.status_code == 429
    assert len(servidor.requisicoes) == 1  # max_retries=0: sem novas tentativas escondidas


# ------------------------------------------------------ OpenAI e OpenRouter


def test_openai_streaming_e_parametros(servidor):
    servidor.roteiro = [("texto", ["Um ", "dois"])]
    p = ProvedorCompativelOpenAI("OpenAI", "gpt-5-mini", "chave-oa", 30, "Professor", base_url=servidor.url)
    assert list(p.gerar(PEDIDO)) == ["Um ", "dois"]
    corpo = servidor.requisicoes[0]["corpo"]
    assert servidor.requisicoes[0]["caminho"].endswith("/chat/completions")
    assert corpo["messages"][0] == {"role": "system", "content": "Você é um professor."}
    assert corpo["messages"][1] == {"role": "user", "content": "Oi"}
    assert corpo["max_completion_tokens"] == 321
    assert "max_tokens" not in corpo
    assert servidor.requisicoes[0]["cabecalhos"]["authorization"] == "Bearer chave-oa"


def test_openrouter_usa_max_tokens_e_cabecalhos_do_app(servidor):
    servidor.roteiro = [("texto", ["ok"])]
    p = ProvedorCompativelOpenAI(
        "OpenRouter", "google/gemma-4-31b-it:free", "k", 30, "Professor", base_url=servidor.url
    )
    assert list(p.gerar(PEDIDO)) == ["ok"]
    req = servidor.requisicoes[0]
    assert req["corpo"]["max_tokens"] == 321
    assert req["corpo"]["model"] == "google/gemma-4-31b-it:free"
    assert req["cabecalhos"]["x-title"] == "Professor"


def test_openrouter_aponta_para_url_oficial_por_padrao():
    p = ProvedorCompativelOpenAI("OpenRouter", "m", "k", 30, "Professor")
    assert str(p._cliente.base_url).rstrip("/") == "https://openrouter.ai/api/v1"


def test_openai_tenta_sem_temperatura_quando_modelo_recusa(servidor):
    servidor.roteiro = [
        ("erro", 400, "Unsupported value: 'temperature' does not support 0.5 with this model."),
        ("texto", ["ok"]),
    ]
    p = ProvedorCompativelOpenAI("OpenAI", "gpt-5-mini", "k", 30, "Professor", base_url=servidor.url)
    assert list(p.gerar(PEDIDO)) == ["ok"]
    assert "temperature" not in servidor.requisicoes[1]["corpo"]


def test_outro_erro_400_nao_repete(servidor):
    servidor.roteiro = [("erro", 400, "invalid model")]
    p = ProvedorCompativelOpenAI("OpenAI", "gpt-x", "k", 30, "Professor", base_url=servidor.url)
    with pytest.raises(Exception):
        list(p.gerar(PEDIDO))
    assert len(servidor.requisicoes) == 1


# ------------------------------------------ roteador + SDKs de verdade (T9)


def test_t9_troca_automatica_com_sdks_reais(servidor, config_real):
    """OpenRouter devolve 429, a Anthropic responde. Tudo pelo servidor falso."""
    servidor.roteiro = [("erro", 429, "free model rate limited"), ("texto", ["Resposta ", "da Anthropic"])]
    fila = [
        ProvedorCompativelOpenAI("OpenRouter", "google/gemma-4-31b-it:free", "k1", 30, "P", base_url=servidor.url),
        ProvedorAnthropic("claude-haiku-4-5", "k2", 30, base_url=servidor.url),
    ]
    saidas = list(responder("Oi", [], config_real, fila))
    assert saidas[-1] == "Resposta da Anthropic"


# ------------------------------------------------- T12: fila pelas chaves


@pytest.fixture
def config_real() -> Config:
    return Config(
        nome="Professor",
        descricao="d",
        cor_principal="#000000",
        cor_secundaria="#000000",
        logo=Path("assets/logo.png"),
        logo_altura=80,
        provedores=[
            Provedor("openrouter", "google/gemma-4-31b-it:free"),
            Provedor("anthropic", "claude-haiku-4-5"),
            Provedor("openai", "gpt-5-mini"),
        ],
        max_tokens=1024,
        temperatura=0.5,
        tempo_limite_segundos=30,
        max_caracteres_pergunta=2000,
        max_mensagens_historico=10,
        instrucoes="Você é um professor.",
    )


def test_t12_tres_chaves_segue_a_ordem_do_config(config_real):
    ambiente = {"OPENAI_API_KEY": "c", "ANTHROPIC_API_KEY": "b", "OPENROUTER_API_KEY": "a"}
    fila = criar_provedores(config_real, ambiente)
    assert [(p.nome, p.modelo) for p in fila] == [
        ("OpenRouter", "google/gemma-4-31b-it:free"),
        ("Anthropic", "claude-haiku-4-5"),
        ("OpenAI", "gpt-5-mini"),
    ]


@pytest.mark.parametrize(
    "variavel,nome",
    [("OPENROUTER_API_KEY", "OpenRouter"), ("ANTHROPIC_API_KEY", "Anthropic"), ("OPENAI_API_KEY", "OpenAI")],
)
def test_t12_funciona_com_uma_chave_so(variavel, nome, config_real):
    fila = criar_provedores(config_real, {variavel: "chave"})
    assert [p.nome for p in fila] == [nome]


def test_t12_chave_vazia_ou_espacos_nao_conta(config_real):
    assert criar_provedores(config_real, {"OPENAI_API_KEY": "   ", "ANTHROPIC_API_KEY": ""}) == []


def test_t12_chave_de_provedor_fora_do_config_e_ignorada(config_real):
    from dataclasses import replace

    so_anthropic = replace(config_real, provedores=[Provedor("anthropic", "claude-haiku-4-5")])
    fila = criar_provedores(so_anthropic, {"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"})
    assert [p.nome for p in fila] == ["Anthropic"]


def test_t12_ordem_invertida_no_config(config_real):
    from dataclasses import replace

    invertido = replace(config_real, provedores=list(reversed(config_real.provedores)))
    ambiente = {"OPENAI_API_KEY": "c", "ANTHROPIC_API_KEY": "b", "OPENROUTER_API_KEY": "a"}
    assert [p.nome for p in criar_provedores(invertido, ambiente)] == ["OpenAI", "Anthropic", "OpenRouter"]
