"""Fila de provedores com troca automática.

Regras (spec, RF12 a RF19):
- tenta os provedores na ordem da fila;
- se um falhar ANTES da primeira palavra, tenta o próximo;
- se falhar DEPOIS de começar, mantém o texto e avisa (não troca, para não duplicar);
- se todos falharem, mostra o motivo de cada um;
- nunca mostra nem registra chaves; o log não guarda o texto das perguntas.

Parte 2 (RAG): com a base de conhecimento ligada, cada pergunta passa antes
pelo agente/rag.py, que decide se busca no material, se responde "não
encontrei" sem chamar o modelo ou se a base está indisponível.

Parte 3: `eventos(...)` é o coração. Devolve, em ordem, eventos tipados
(fontes, texto, fim ou erro), que o servidor (agente/servidor.py) manda ao
navegador em SSE. `responder(...)` monta, a partir dos mesmos eventos, o
texto ACUMULADO que o chat do Gradio usava.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from agente.config import Config
from agente.erros import traduzir
from agente.provedores import Mensagem, Pedido, Provedor
from agente.rag import MSG_BASE_INDISPONIVEL, BaseRAG, bloco_fontes, e_nao_encontrado
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


@dataclass(frozen=True)
class Evento:
    """Um pedaço da resposta. tipo: "fontes", "texto", "fim" ou "erro" (contrato da spec da Parte 3, 5.4)."""

    tipo: str
    dados: dict[str, Any] = field(default_factory=dict)


def _erro(tipo: str, mensagem: str) -> Evento:
    return Evento("erro", {"tipo": tipo, "mensagem": mensagem})


def eventos(
    pergunta: str,
    historico: Sequence[dict],
    config: Config,
    provedores: Sequence[Provedor],
    rag: BaseRAG | None = None,
) -> Iterator[Evento]:
    pergunta = (pergunta or "").strip()
    if not pergunta:
        return
    if len(pergunta) > config.max_caracteres_pergunta:
        yield _erro("pergunta_longa", msg_pergunta_longa(len(pergunta), config.max_caracteres_pergunta))
        return
    if not provedores:
        log.warning("Nenhum provedor com chave cadastrada.")
        yield _erro("sem_chave", MSG_SEM_CHAVE)
        return

    instrucoes, ultima, contexto = config.instrucoes, pergunta, None
    if rag is not None and config.base_conhecimento.ativa:
        contexto = rag.preparar(pergunta)
        if contexto.tipo == "indisponivel":
            yield _erro("base_indisponivel", MSG_BASE_INDISPONIVEL)
            return
        if contexto.tipo == "nao_encontrado":
            # A frase exata, sem chamar o modelo (RF32).
            yield Evento("texto", {"delta": config.base_conhecimento.mensagem_nao_encontrado})
            yield Evento("fim", {"nao_encontrado": True})
            return
        if contexto.tipo == "material":
            # As fontes saem antes do texto: a busca acontece antes da geração.
            yield Evento(
                "fontes",
                {
                    "fontes": [
                        {"n": n, "fonte": t.fonte, "secao": t.secao, "trecho": t.conteudo}
                        for n, t in enumerate(contexto.trechos, start=1)
                    ]
                },
            )
        instrucoes = f"{config.instrucoes.rstrip()}\n\n{contexto.regras}"
        ultima = contexto.mensagem  # os trechos vão só com a pergunta atual (RF38)

    pedido = Pedido(
        instrucoes=instrucoes,
        mensagens=montar_mensagens(historico, ultima, config.max_mensagens_historico),
        max_tokens=config.max_tokens,
        temperatura=config.temperatura,
    )
    texto = yield from _transmitir(pedido, provedores, config)
    if texto:
        nao_encontrado = e_nao_encontrado(texto, config.base_conhecimento.mensagem_nao_encontrado)
        yield Evento("fim", {"nao_encontrado": bool(contexto is not None and nao_encontrado)})


def responder(
    pergunta: str,
    historico: Sequence[dict],
    config: Config,
    provedores: Sequence[Provedor],
    rag: BaseRAG | None = None,
) -> Iterator[str]:
    """Texto acumulado a cada pedaço, com as fontes escritas pelo app no fim (formato do chat Gradio)."""
    texto, fontes = "", []
    for evento in eventos(pergunta, historico, config, provedores, rag):
        if evento.tipo == "fontes":
            fontes = evento.dados["fontes"]
        elif evento.tipo == "texto":
            texto += evento.dados["delta"]
            yield texto
        elif evento.tipo == "erro":
            yield texto + evento.dados["mensagem"] if texto else evento.dados["mensagem"]
        elif evento.tipo == "fim" and fontes and not evento.dados["nao_encontrado"]:
            yield texto + bloco_fontes(fontes)  # escritas pelo app, não pelo modelo (RF34)


def _transmitir(pedido: Pedido, provedores: Sequence[Provedor], config: Config) -> Iterator[Evento]:
    """Tenta a fila de provedores. Devolve (no return) o texto completo, ou "" se não terminou bem."""
    chaves = tuple(p.chave for p in provedores)
    falhas: list[str] = []

    for provedor in provedores:
        rotulo = f"{provedor.nome} ({provedor.modelo})"
        texto = ""
        try:
            for pedaco in provedor.gerar(pedido):
                if not pedaco:
                    continue
                texto += pedaco
                yield Evento("texto", {"delta": pedaco})
        except Exception as erro:  # noqa: BLE001 - qualquer falha do provedor vira mensagem amigável
            motivo = traduzir(erro, config.tempo_limite_segundos, chaves)
            if texto:
                # Já começou a responder: não troca de provedor (a resposta ficaria duplicada).
                log.warning("%s interrompeu a resposta: %s", rotulo, motivo)
                yield _erro("interrompida", msg_interrompida(motivo))
                return ""
            log.warning("%s falhou antes de responder: %s. Tentando o próximo.", rotulo, motivo)
            falhas.append(f"• {rotulo}: {motivo}.")
            continue
        if texto:
            log.info("Resposta enviada por %s.", rotulo)
            return texto
        log.warning("%s terminou sem enviar texto. Tentando o próximo.", rotulo)
        falhas.append(f"• {rotulo}: o provedor não devolveu nenhum texto.")

    mensagem = "\n".join([MSG_TODOS_FALHARAM, *falhas, "", MSG_TENTE_DE_NOVO])
    yield _erro("provedores", ocultar_chaves(mensagem, chaves))
    return ""
