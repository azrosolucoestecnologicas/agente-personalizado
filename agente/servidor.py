"""Servidor da Parte 3: a API do assistente e a entrega da interface, num endereço só.

Rotas (contrato na spec da Parte 3, seção 5):
    GET  /api/saude      o servidor está pronto? (health check do Railway)
    GET  /api/config     o que a interface precisa saber (sem segredos)
    GET  /api/logo       a logo do config.yaml
    POST /api/perguntar  a pergunta, respondida em streaming (SSE)
    /                    a interface compilada (frontend/dist)

Rodar no computador:
    uvicorn agente.servidor:app --port 8000      (depois abra http://127.0.0.1:8000)

As chaves ficam só nas variáveis de ambiente do servidor. O navegador nunca
recebe chave, prompt de sistema, nome de modelo nem endereço do banco.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agente.banco import ErroBanco
from agente.config import RAIZ_PROJETO, Config, ErroConfig, carregar_config
from agente.limites import LimiteDeUso, ip_do_visitante, mascarar_ip
from agente.provedores import Provedor, criar_provedores
from agente.rag import BaseRAG, criar_rag
from agente.roteador import Evento, eventos, msg_pergunta_longa
from agente.segredos import ocultar_chaves

log = logging.getLogger("agente")

PASTA_INTERFACE = RAIZ_PROJETO / "frontend" / "dist"
MAX_SIMULTANEAS = 10  # perguntas respondidas ao mesmo tempo (RF62)
MAX_HISTORICO = 20  # mensagens anteriores aceitas no pedido
MAX_TEXTO_HISTORICO = 8000  # caracteres por mensagem do histórico
CACHE_SAUDE = 60.0  # segundos que a contagem de trechos fica guardada
CARREGAR = object()  # "monte o RAG ao iniciar" (padrão); os testes passam um RAG pronto

MSG_CARREGANDO = "O assistente está iniciando. Tente em alguns segundos."
MSG_OCUPADO = "Muita gente perguntando agora. Tente de novo em alguns segundos."
CABECALHOS_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    ),
}
PAGINA_SEM_INTERFACE = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>Assistente</title><body style="font-family:sans-serif;max-width:40rem;margin:4rem auto">
<h1>A API está no ar</h1><p>A interface ainda não foi compilada (pasta <code>frontend/dist</code>).
Rode <code>npm run build</code> dentro de <code>frontend/</code>.</p></body></html>"""


# ------------------------------------------------------------ o pedido


class MensagemHistorico(BaseModel):
    model_config = ConfigDict(extra="forbid")

    papel: Literal["usuario", "assistente"]
    texto: str = Field(max_length=MAX_TEXTO_HISTORICO)


class Pergunta(BaseModel):
    """Só isto pode vir do navegador: não dá para pedir outro modelo, temperatura ou prompt."""

    model_config = ConfigDict(extra="forbid")

    mensagem: str
    historico: list[MensagemHistorico] = Field(default_factory=list, max_length=MAX_HISTORICO)

    @field_validator("mensagem")
    @classmethod
    def _nao_vazia(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("a pergunta está vazia")
        return valor.strip()


def _explicar_validacao(erros: Sequence[Mapping[str, Any]]) -> str:
    """Erros do Pydantic em português, um por linha."""
    frases = []
    for erro in erros:
        campo = ".".join(str(p) for p in erro.get("loc", ()) if p != "body")
        tipo = erro.get("type", "")
        if tipo == "json_invalid":
            frases.append("o corpo do pedido não é um JSON válido")
        elif tipo == "missing":
            frases.append(f"falta o campo `{campo}`")
        elif tipo == "extra_forbidden":
            frases.append(f"o campo `{campo}` não é aceito (envie só `mensagem` e `historico`)")
        elif tipo == "too_long" and campo == "historico":
            frases.append(f"o histórico pode ter no máximo {MAX_HISTORICO} mensagens")
        elif tipo == "string_too_long":
            frases.append(f"`{campo}` passa de {MAX_TEXTO_HISTORICO} caracteres")
        elif tipo == "literal_error":
            frases.append(f"`{campo}` deve ser 'usuario' ou 'assistente'")
        elif tipo == "value_error":
            frases.append(str(erro.get("ctx", {}).get("error", "valor inválido")))
        else:
            frases.append(f"`{campo or 'pedido'}` em formato inválido")
    return "Pedido inválido: " + "; ".join(dict.fromkeys(frases)) + "."


def _sse(evento: Evento) -> str:
    return f"event: {evento.tipo}\ndata: {json.dumps(evento.dados, ensure_ascii=False)}\n\n"


# ------------------------------------------------------------ o servidor


def criar_servidor(
    config: Config,
    provedores: Sequence[Provedor] | None = None,
    rag: Any = CARREGAR,
    ambiente: Mapping[str, str] | None = None,
    pasta_interface: Path = PASTA_INTERFACE,
    relogio=time.time,
) -> FastAPI:
    """Monta o app. Os testes passam provedores, RAG e relógio falsos; em produção, tudo vem do ambiente."""
    ambiente = os.environ if ambiente is None else ambiente
    provedores = criar_provedores(config, ambiente) if provedores is None else list(provedores)
    chaves = tuple(p.chave for p in provedores)
    limite = LimiteDeUso(config.servidor.perguntas_por_minuto, config.servidor.perguntas_por_dia, relogio)
    vagas = threading.BoundedSemaphore(MAX_SIMULTANEAS)
    versao = (ambiente.get("RAILWAY_GIT_COMMIT_SHA") or "local")[:7]
    estado: dict[str, Any] = {"pronto": rag is not CARREGAR, "rag": None if rag is CARREGAR else rag}
    contagem: dict[str, Any] = {"quando": -CACHE_SAUDE, "trechos": None}

    def carregar() -> None:
        """RF58: carrega o modelo e conta os trechos. Enquanto isso, /api/saude responde 503."""
        try:
            estado["rag"] = criar_rag(config.base_conhecimento, ambiente)
        finally:
            estado["pronto"] = True

    @asynccontextmanager
    async def ciclo_de_vida(_app: FastAPI):
        if provedores:
            log.info("Fila de provedores: %s", " → ".join(f"{p.nome} ({p.modelo})" for p in provedores))
        else:
            log.warning("Nenhuma chave de IA cadastrada: o chat vai explicar como cadastrar.")
        if not estado["pronto"]:
            threading.Thread(target=carregar, name="carregar-base", daemon=True).start()
        yield

    app = FastAPI(title=config.nome, docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo_de_vida)

    @app.middleware("http")
    async def seguranca(request: Request, chamar_proximo):
        resposta = await chamar_proximo(request)
        for nome, valor in CABECALHOS_SEGURANCA.items():
            resposta.headers.setdefault(nome, valor)
        return resposta

    @app.exception_handler(RequestValidationError)
    async def pedido_invalido(_request: Request, erro: RequestValidationError):
        return JSONResponse(
            status_code=422, content={"erro": "pedido_invalido", "mensagem": _explicar_validacao(erro.errors())}
        )

    # ----------------------------------------------------------- /api/saude
    @app.get("/api/saude")
    def saude():
        if not estado["pronto"]:
            return JSONResponse(
                status_code=503, content={"status": "carregando", "versao": versao, "motivo": MSG_CARREGANDO}
            )
        base: BaseRAG | None = estado["rag"]
        if base is None:  # base de conhecimento desligada no config.yaml
            return {"status": "ok", "versao": versao, "trechos_na_producao": None}
        if base.motivo_indisponivel:
            motivo = ocultar_chaves(base.motivo_indisponivel, chaves)
            return JSONResponse(status_code=503, content={"status": "indisponivel", "versao": versao, "motivo": motivo})
        agora = time.monotonic()
        if agora - contagem["quando"] >= CACHE_SAUDE:
            try:
                contagem["trechos"] = base.banco.contar("producao")
                contagem["quando"] = agora
            except ErroBanco as erro:
                motivo = ocultar_chaves(str(erro), chaves)
                return JSONResponse(
                    status_code=503, content={"status": "indisponivel", "versao": versao, "motivo": motivo}
                )
        return {"status": "ok", "versao": versao, "trechos_na_producao": contagem["trechos"]}

    # ----------------------------------------------------------- /api/config
    @app.get("/api/config")
    def configuracao():
        """Só o que a tela usa. Nunca: instruções, provedores, modelos, chaves, endereço do banco."""
        return {
            "nome": config.nome,
            "descricao": config.descricao,
            "exemplos": list(config.exemplos),
            "logo_url": "/api/logo",
            "cores": {
                "principal": config.cor_principal,
                "secundaria": config.cor_secundaria,
                "destaque": config.cor_destaque or config.cor_principal,
            },
            "limites": {"max_caracteres_pergunta": config.max_caracteres_pergunta},
            "mensagem_nao_encontrado": config.base_conhecimento.mensagem_nao_encontrado,
        }

    @app.get("/api/logo")
    def logo():
        if not config.logo.is_file():
            return JSONResponse(
                status_code=404, content={"erro": "nao_encontrado", "mensagem": "A logo não foi encontrada."}
            )
        return FileResponse(config.logo, headers={"Cache-Control": "public, max-age=3600"})

    # ------------------------------------------------------- /api/perguntar
    @app.post("/api/perguntar")
    def perguntar(dados: Pergunta, request: Request):
        if len(dados.mensagem) > config.max_caracteres_pergunta:
            mensagem = msg_pergunta_longa(len(dados.mensagem), config.max_caracteres_pergunta)
            return JSONResponse(status_code=413, content={"erro": "pergunta_longa", "mensagem": mensagem})
        if not estado["pronto"]:
            return JSONResponse(status_code=503, content={"erro": "carregando", "mensagem": MSG_CARREGANDO})
        if not vagas.acquire(blocking=False):
            return JSONResponse(status_code=503, content={"erro": "ocupado", "mensagem": MSG_OCUPADO})
        ip = ip_do_visitante(request.headers, request.client.host if request.client else None)
        espera = limite.tentar(ip)
        if espera is not None:
            vagas.release()
            log.info("Limite de uso atingido por %s: esperar %d s.", mascarar_ip(ip), espera)
            return JSONResponse(
                status_code=429,
                content={
                    "erro": "limite",
                    "mensagem": f"Muitas perguntas seguidas. Tente de novo em {espera} segundos.",
                    "tentar_em": espera,
                },
                headers={"Retry-After": str(espera)},
            )
        historico = [
            {"role": "user" if m.papel == "usuario" else "assistant", "content": m.texto} for m in dados.historico
        ]
        return StreamingResponse(
            _responder(dados.mensagem, historico),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def _responder(mensagem: str, historico: list[dict]) -> Iterator[str]:
        inicio, tipo = time.monotonic(), "conversa"
        try:
            for evento in eventos(mensagem, historico, config, provedores, estado["rag"]):
                if evento.tipo == "fontes":
                    tipo = "material"
                elif evento.tipo == "fim" and evento.dados.get("nao_encontrado"):
                    tipo = "não encontrei"
                elif evento.tipo == "erro":
                    tipo = f"erro ({evento.dados['tipo']})"
                yield _sse(evento)
        finally:
            vagas.release()
            # RF61: só tamanho, tipo e tempo. Nunca o texto da pergunta.
            log.info("Pergunta: %d caracteres · resposta: %s · %.1f s", len(mensagem), tipo, time.monotonic() - inicio)

    # ------------------------------------------------------- a interface
    raiz_interface = pasta_interface.resolve()
    tem_interface = (raiz_interface / "index.html").is_file()

    @app.get("/{caminho:path}", include_in_schema=False)
    def interface(caminho: str):
        if caminho == "api" or caminho.startswith("api/"):
            return JSONResponse(
                status_code=404, content={"erro": "nao_encontrado", "mensagem": "Rota da API não encontrada."}
            )
        if not tem_interface:
            return HTMLResponse(PAGINA_SEM_INTERFACE)
        arquivo = (raiz_interface / caminho).resolve()
        if caminho and arquivo.is_file() and arquivo.is_relative_to(raiz_interface):
            return FileResponse(arquivo)
        return FileResponse(raiz_interface / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def _app_do_ambiente() -> FastAPI:
    """O app que o uvicorn sobe. Config inválido: não sobe e explica no log (RF57)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = carregar_config()
    except ErroConfig as erro:
        print("O config.yaml tem problemas:\n" + "\n".join(erro.erros), file=sys.stderr)
        raise SystemExit(1) from None
    return criar_servidor(config)


app = _app_do_ambiente()
