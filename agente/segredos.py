"""Formatos de chaves de API que nunca podem aparecer no código.

Usado pela validação do config.yaml e pelo scripts/procurar_chaves.py.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
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
    ("chave secreta do Supabase", re.compile(r"(?<![A-Za-z0-9_])sb_secret_[A-Za-z0-9_\-]{20,}")),
]
# Chave antiga do Supabase em formato JWT. Só a de papel service_role é secreta
# (grava e ignora a RLS); a de papel anon é pública por natureza.
TIPO_JWT_SECRETO = "chave service_role do Supabase (JWT)"
_JWT = re.compile(r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{10,}\.(eyJ[A-Za-z0-9_\-]{10,})\.[A-Za-z0-9_\-]{10,}")


def _jwt_service_role(payload: str) -> bool:
    """O miolo do JWT (base64) diz "role": "service_role"?"""
    try:
        dados = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (binascii.Error, ValueError):
        return False
    return isinstance(dados, dict) and dados.get("role") == "service_role"


# Pega chaves em formato desconhecido quando o nome da variável recebe um
# valor escrito direto no código, ex.: OPENAI_API_KEY = "abc123...".
# Ler do ambiente (os.environ["OPENAI_API_KEY"]) não é pego.
TIPO_ATRIBUICAO = "chave escrita direto no código"

# Chaves FALSAS já conhecidas (de exemplos e testes antigos), guardadas só pela
# impressão digital SHA-256, para a varredura não acusá-las. Nunca coloque aqui
# o hash de uma chave de verdade: chave real vazada deve ser revogada.
FALSAS_CONHECIDAS = {
    "2c975580f00e5130cb4bf306d739321946a897cd8940d75da0908ea8159f929d": "exemplo de teste da tarefa 1 (alfabeto em ordem)",
}


def impressao(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


_ATRIBUICAO = re.compile(
    r"(?:OPENROUTER_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY|HF_TOKEN|SUPABASE_SECRET_KEY|SUPABASE_SERVICE_ROLE_KEY)[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-]{16,})"
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
            if impressao(m.group(0)) not in FALSAS_CONHECIDAS:
                achados.append(Achado(tipo, mascarar(m.group(0))))
    for m in _JWT.finditer(texto):
        if _jwt_service_role(m.group(1)):
            ocupados.append(m.span())
            if impressao(m.group(0)) not in FALSAS_CONHECIDAS:
                achados.append(Achado(TIPO_JWT_SECRETO, mascarar(m.group(0))))
    for m in _ATRIBUICAO.finditer(texto):
        if any(ini <= m.start(1) < fim for ini, fim in ocupados):
            continue
        if impressao(m.group(1)) not in FALSAS_CONHECIDAS:
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
    return _JWT.sub(lambda m: "[chave oculta]" if _jwt_service_role(m.group(1)) else m.group(0), texto)
