"""Formatos de chaves de API que nunca podem aparecer no código.

Usado pela validação do config.yaml e pelo scripts/procurar_chaves.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (descrição, expressão regular). A ordem importa: os formatos mais
# específicos vêm antes do genérico "sk-".
PADROES_CHAVE: list[tuple[str, re.Pattern[str]]] = [
    ("chave do OpenRouter", re.compile(r"sk-or-[A-Za-z0-9_\-]{20,}")),
    ("chave da Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("chave da OpenAI", re.compile(r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{20,}")),
    ("chave no formato sk-", re.compile(r"(?<![A-Za-z0-9_\-])sk-[A-Za-z0-9]{32,}")),
    ("token do Hugging Face", re.compile(r"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{30,}")),
]
# Pega chaves em formato desconhecido quando o nome da variável recebe um
# valor escrito direto no código, ex.: OPENAI_API_KEY = "abc123...".
# Ler do ambiente (os.environ["OPENAI_API_KEY"]) não é pego.
TIPO_ATRIBUICAO = "chave escrita direto no código"
_ATRIBUICAO = re.compile(
    r"(?:OPENROUTER_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY|HF_TOKEN)[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-]{16,})"
)


@dataclass(frozen=True)
class Achado:
    tipo: str
    trecho: str  # já mascarado: nunca guarda a chave inteira


def mascarar(valor: str) -> str:
    """Mostra só o começo da chave: 'sk-ant-api03-abc…' vira 'sk-ant…(oculto)'."""
    return f"{valor[:6]}…(oculto)"


def procurar_em_texto(texto: str) -> list[Achado]:
    """Devolve as chaves encontradas no texto, já mascaradas."""
    achados: list[Achado] = []
    ocupados: list[tuple[int, int]] = []
    for tipo, padrao in PADROES_CHAVE:
        for m in padrao.finditer(texto):
            if any(ini <= m.start() < fim for ini, fim in ocupados):
                continue  # já contado por um padrão mais específico
            ocupados.append(m.span())
            achados.append(Achado(tipo, mascarar(m.group(0))))
    for m in _ATRIBUICAO.finditer(texto):
        if any(ini <= m.start(1) < fim for ini, fim in ocupados):
            continue
        achados.append(Achado(TIPO_ATRIBUICAO, mascarar(m.group(1))))
    return achados


def tem_chave(texto: str) -> bool:
    return bool(procurar_em_texto(texto))


def ocultar_chaves(texto: str, chaves: list[str] | tuple[str, ...] = ()) -> str:
    """Troca por '[chave oculta]' as chaves conhecidas e tudo o que tiver formato de chave."""
    for chave in chaves:
        if chave:
            texto = texto.replace(chave, "[chave oculta]")
    for _, padrao in PADROES_CHAVE:
        texto = padrao.sub("[chave oculta]", texto)
    return texto
