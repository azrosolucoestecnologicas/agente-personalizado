"""Fila de provedores com troca automática.

Regras (spec, RF12 a RF19):
- tenta os provedores na ordem da fila;
- se um falhar ANTES da primeira palavra, tenta o próximo;
- se falhar DEPOIS de começar, mantém o texto e avisa (não troca, para não duplicar);
- se todos falharem, mostra o motivo de cada um;
- nunca mostra nem registra chaves; o log não guarda o texto das perguntas.

`responder(...)` devolve o texto ACUMULADO a cada pedaço, que é o formato
que o chat do Gradio usa para mostrar a resposta palavra por palavra.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from typing import Any

from agente.config import Config
from agente.erros import traduzir
from agente.provedores import Mensagem, Pedido, Provedor
from agente.segredos import ocultar_chaves

log = logging.getLogger("agente")

MSG_SEM_CHAVE = (
    "⚠️ Nenhuma chave de IA configurada. Cadastre OPENROUTER_API_KEY, ANTHROPIC_API_KEY "
    "ou OPENAI_API_KEY nos secrets do Space (Settings → Variables and secrets → New secret)."
)
MSG_TODOS_FALHARAM = "😕 Não consegui responder agora. Motivos:"
MSG_TENTE_DE_NOVO = "Tente de novo em alguns instantes."


def msg_pergunta_longa(tamanho: int, maximo: int) -> str:
    return (
        f"✋ Sua pergunta tem {tamanho} caracteres e o limite é {maximo}. Resuma um pouco ou divida em partes menores."
    )


def msg_interrompida(motivo: str) -> str:
    return f"\n\n⚠️ A resposta foi interrompida ({motivo}). Tente novamente."


def _texto_de(conteudo: Any) -> str:
    """Extrai o texto de uma mensagem do histórico do Gradio (texto ou lista de partes)."""
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, dict):
        return str(conteudo.get("text") or "")
    if isinstance(conteudo, (list, tuple)):
        return "\n".join(filter(None, (_texto_de(parte) for parte in conteudo)))
    return ""


def montar_mensagens(historico: Sequence[dict], pergunta: str, max_historico: int) -> list[Mensagem]:
    """Últimas `max_historico` mensagens + a pergunta. A primeira sempre é do usuário."""
    anteriores: list[Mensagem] = []
    for item in historico or []:
        papel = item.get("role") if isinstance(item, dict) else None
        texto = _texto_de(item.get("content")) if papel else ""
        if papel in ("user", "assistant") and texto.strip():
            anteriores.append({"role": papel, "content": texto})
    anteriores = anteriores[-max_historico:] if max_historico else []
    while anteriores and anteriores[0]["role"] != "user":
        anteriores.pop(0)
    return [*anteriores, {"role": "user", "content": pergunta}]


def responder(
    pergunta: str,
    historico: Sequence[dict],
    config: Config,
    provedores: Sequence[Provedor],
) -> Iterator[str]:
    pergunta = (pergunta or "").strip()
    if not pergunta:
        return
    if len(pergunta) > config.max_caracteres_pergunta:
        yield msg_pergunta_longa(len(pergunta), config.max_caracteres_pergunta)
        return
    if not provedores:
        log.warning("Nenhum provedor com chave cadastrada.")
        yield MSG_SEM_CHAVE
        return

    chaves = tuple(p.chave for p in provedores)
    pedido = Pedido(
        instrucoes=config.instrucoes,
        mensagens=montar_mensagens(historico, pergunta, config.max_mensagens_historico),
        max_tokens=config.max_tokens,
        temperatura=config.temperatura,
    )
    falhas: list[str] = []

    for provedor in provedores:
        rotulo = f"{provedor.nome} ({provedor.modelo})"
        texto = ""
        try:
            for pedaco in provedor.gerar(pedido):
                if not pedaco:
                    continue
                texto += pedaco
                yield texto
        except Exception as erro:  # noqa: BLE001 - qualquer falha do provedor vira mensagem amigável
            motivo = traduzir(erro, config.tempo_limite_segundos, chaves)
            if texto:
                # Já começou a responder: não troca de provedor (a resposta ficaria duplicada).
                log.warning("%s interrompeu a resposta: %s", rotulo, motivo)
                yield texto + msg_interrompida(motivo)
                return
            log.warning("%s falhou antes de responder: %s. Tentando o próximo.", rotulo, motivo)
            falhas.append(f"• {rotulo}: {motivo}.")
            continue
        if texto:
            log.info("Resposta enviada por %s.", rotulo)
            return
        log.warning("%s terminou sem enviar texto. Tentando o próximo.", rotulo)
        falhas.append(f"• {rotulo}: o provedor não devolveu nenhum texto.")

    mensagem = "\n".join([MSG_TODOS_FALHARAM, *falhas, "", MSG_TENTE_DE_NOVO])
    yield ocultar_chaves(mensagem, chaves)
