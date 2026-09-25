"""Adaptadores dos três provedores de IA, todos com a mesma "cara".

Cada provedor tem um método `gerar(...)` que devolve os pedaços de texto
da resposta, um a um (streaming). Assim o roteador trata todos igual.

- Anthropic: SDK oficial `anthropic`.
- OpenAI e OpenRouter: SDK `openai` (no OpenRouter, com base_url própria).
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol

from agente.config import Config
from agente.erros import recusou_parametro

URL_OPENROUTER = "https://openrouter.ai/api/v1"

# nome no config.yaml -> (nome para exibir, variável de ambiente com a chave)
PROVEDORES = {
    "openrouter": ("OpenRouter", "OPENROUTER_API_KEY"),
    "anthropic": ("Anthropic", "ANTHROPIC_API_KEY"),
    "openai": ("OpenAI", "OPENAI_API_KEY"),
}

Mensagem = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}


@dataclass(frozen=True)
class Pedido:
    """Tudo o que o provedor precisa para responder."""

    instrucoes: str
    mensagens: list[Mensagem]
    max_tokens: int
    temperatura: float


def _sem_temperatura_se_recusada(stream, pedido: Pedido) -> Iterator[str]:
    """Tenta com 'temperature'; se o modelo recusar esse parâmetro, tenta sem.

    Modelos mais novos (ex.: Claude Sonnet 5, GPT-5) não aceitam 'temperature'.
    Só tenta de novo se nenhum texto tiver saído ainda.
    """
    saiu_texto = False
    try:
        for pedaco in stream(pedido, com_temperatura=True):
            saiu_texto = True
            yield pedaco
    except Exception as erro:
        if saiu_texto or not recusou_parametro(erro, "temperature"):
            raise
        yield from stream(pedido, com_temperatura=False)


class Provedor(Protocol):
    nome: str  # nome para exibir, ex.: "OpenRouter"
    modelo: str
    chave: str

    def gerar(self, pedido: Pedido) -> Iterator[str]: ...


class ProvedorAnthropic:
    def __init__(self, modelo: str, chave: str, tempo_limite: int, base_url: str | None = None):
        import anthropic

        self.nome, self.modelo, self.chave = "Anthropic", modelo, chave
        # max_retries=0: se falhar, a troca automática já tenta o próximo provedor.
        self._cliente = anthropic.Anthropic(api_key=chave, base_url=base_url, timeout=tempo_limite, max_retries=0)

    def gerar(self, pedido: Pedido) -> Iterator[str]:
        return _sem_temperatura_se_recusada(self._stream, pedido)

    def _stream(self, pedido: Pedido, com_temperatura: bool) -> Iterator[str]:
        extra = {"temperature": pedido.temperatura} if com_temperatura else None
        with self._cliente.messages.stream(
            model=self.modelo,
            max_tokens=pedido.max_tokens,
            system=pedido.instrucoes,
            messages=pedido.mensagens,
            extra_body=extra,
        ) as stream:
            yield from stream.text_stream


class ProvedorCompativelOpenAI:
    """OpenAI e OpenRouter usam o mesmo formato (Chat Completions)."""

    def __init__(
        self, nome: str, modelo: str, chave: str, tempo_limite: int, nome_app: str, base_url: str | None = None
    ):
        import openai

        self.nome, self.modelo, self.chave = nome, modelo, chave
        self._eh_openrouter = nome == "OpenRouter"
        opcoes: dict = {"base_url": base_url} if base_url else {}
        if self._eh_openrouter:
            # Cabeçalhos opcionais que identificam o app no painel do OpenRouter.
            opcoes = {
                "base_url": base_url or URL_OPENROUTER,
                "default_headers": {"HTTP-Referer": "https://huggingface.co/spaces", "X-Title": nome_app},
            }
        self._cliente = openai.OpenAI(api_key=chave, timeout=tempo_limite, max_retries=0, **opcoes)

    def gerar(self, pedido: Pedido) -> Iterator[str]:
        return _sem_temperatura_se_recusada(self._stream, pedido)

    def _stream(self, pedido: Pedido, com_temperatura: bool) -> Iterator[str]:
        parametros: dict = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": pedido.instrucoes}, *pedido.mensagens],
            "stream": True,
        }
        # A OpenAI usa 'max_completion_tokens'; o OpenRouter usa 'max_tokens'.
        parametros["max_tokens" if self._eh_openrouter else "max_completion_tokens"] = pedido.max_tokens
        if com_temperatura:
            parametros["temperature"] = pedido.temperatura
        for pedaco in self._cliente.chat.completions.create(**parametros):
            if pedaco.choices and pedaco.choices[0].delta and pedaco.choices[0].delta.content:
                yield pedaco.choices[0].delta.content


def criar_provedores(config: Config, ambiente: Mapping[str, str] | None = None) -> list[Provedor]:
    """Monta a fila: a ordem do config.yaml, só com quem tem chave cadastrada."""
    ambiente = os.environ if ambiente is None else ambiente
    fila: list[Provedor] = []
    for item in config.provedores:
        nome_exibicao, variavel = PROVEDORES[item.nome]
        chave = (ambiente.get(variavel) or "").strip()
        if not chave:
            continue
        if item.nome == "anthropic":
            fila.append(ProvedorAnthropic(item.modelo, chave, config.tempo_limite_segundos))
        else:
            fila.append(
                ProvedorCompativelOpenAI(nome_exibicao, item.modelo, chave, config.tempo_limite_segundos, config.nome)
            )
    return fila
