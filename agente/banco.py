"""Conversa com o Supabase pela API REST (PostgREST), usando httpx (spec da Parte 2).

Quem usa qual chave:
- Space: SUPABASE_PUBLISHABLE_KEY (só lê a coleção 'producao' e busca);
- GitHub Actions: SUPABASE_SECRET_KEY (grava, apaga e promove).

As chaves novas (sb_publishable_..., sb_secret_...) vão SÓ no cabeçalho
"apikey". Mandá-las também em "Authorization: Bearer" faz o Supabase
recusar com "Invalid JWT". As chaves antigas (JWT, começam com "eyJ")
vão nos dois cabeçalhos.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from agente.segredos import ocultar_chaves

COLECOES = ("teste", "producao")
LOTE_GRAVACAO = 50  # trechos por requisição: cada um carrega 768 números


class ErroBanco(Exception):
    """O banco recusou o pedido ou não respondeu. A mensagem nunca contém a chave."""


@dataclass(frozen=True)
class Resultado:
    """Uma linha devolvida por buscar_hibrido."""

    id: int
    fonte: str
    secao: str
    conteudo: str
    similaridade: float
    nota_rrf: float
    pos_palavras: int | None  # posição na busca por palavras (None = não apareceu)
    pos_sentido: int | None  # posição na busca por sentido


def vetor_texto(vetor: Sequence[float]) -> str:
    """Formato que o pgvector entende: "[0.1,0.2,...]"."""
    return "[" + ",".join(f"{float(x):.7g}" for x in vetor) + "]"


class Banco:
    def __init__(self, url: str, chave: str, tempo_limite: float = 15.0, cliente: httpx.Client | None = None):
        url = (url or "").strip().rstrip("/")
        if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
            raise ErroBanco("SUPABASE_URL deve ser o endereço do projeto, ex.: https://abcd1234.supabase.co")
        if not chave:
            raise ErroBanco("A chave do Supabase está vazia.")
        self.url = url
        self._chave = chave
        cabecalhos = {"apikey": chave, "Content-Type": "application/json"}
        if chave.startswith("eyJ"):  # chave antiga (JWT)
            cabecalhos["Authorization"] = f"Bearer {chave}"
        self._cliente = cliente or httpx.Client(timeout=tempo_limite)
        self._cabecalhos = cabecalhos

    # ------------------------------------------------------------ interno

    def _pedir(self, metodo: str, caminho: str, **kwargs: Any) -> httpx.Response:
        cabecalhos = {**self._cabecalhos, **kwargs.pop("headers", {})}
        try:
            resposta = self._cliente.request(metodo, f"{self.url}{caminho}", headers=cabecalhos, **kwargs)
        except httpx.TimeoutException:
            raise ErroBanco("O Supabase demorou demais para responder (o projeto pode estar pausado).") from None
        except httpx.HTTPError as erro:
            raise ErroBanco(self._limpar(f"Não consegui conectar ao Supabase ({type(erro).__name__}).")) from None
        if resposta.status_code >= 400:
            raise ErroBanco(self._explicar(resposta))
        return resposta

    def _limpar(self, texto: str) -> str:
        return ocultar_chaves(texto, [self._chave])

    def _explicar(self, resposta: httpx.Response) -> str:
        try:
            dados = resposta.json()
            detalhe = dados.get("message") or dados.get("msg") or dados.get("error") or str(dados)
        except ValueError:
            detalhe = resposta.text[:300]
        codigo = resposta.status_code
        if codigo == 401 or "Invalid API key" in detalhe or "Invalid JWT" in detalhe:
            dica = "A chave foi recusada: confira se o secret tem a chave inteira e se ela é deste projeto."
        elif codigo == 403 or "permission denied" in detalhe:
            dica = "Permissão negada: essa chave não pode fazer isso (a publicável só lê a produção)."
        elif codigo == 404 or "Could not find the function" in detalhe:
            dica = "Tabela ou função não encontrada: rode o supabase/esquema.sql no SQL Editor."
        elif "dimensions" in detalhe:
            dica = "O vetor não tem o tamanho que o banco espera: o modelo de embedding não é o mesmo do banco."
        elif codigo >= 500:
            dica = "Erro no servidor do Supabase (o projeto pode estar pausado ou reiniciando)."
        else:
            dica = "O Supabase recusou o pedido."
        return self._limpar(f"{dica} (HTTP {codigo}: {detalhe})")

    def _rpc(self, funcao: str, argumentos: Mapping[str, Any] | None = None) -> Any:
        return self._pedir("POST", f"/rest/v1/rpc/{funcao}", json=dict(argumentos or {})).json()

    # ---------------------------------------------------------- consultas

    def buscar(
        self,
        consulta: str,
        embedding: Sequence[float],
        quantidade: int = 4,
        peso_palavras: float = 1.0,
        peso_sentido: float = 1.0,
        colecao: str = "producao",
    ) -> list[Resultado]:
        """Busca híbrida (palavras + sentido, fundidas por RRF) dentro do banco."""
        linhas = self._rpc(
            "buscar_hibrido",
            {
                "consulta": consulta,
                "consulta_embedding": vetor_texto(embedding),
                "quantidade": quantidade,
                "peso_palavras": peso_palavras,
                "peso_sentido": peso_sentido,
                "p_colecao": colecao,
            },
        )
        return [
            Resultado(
                id=int(linha["id"]),
                fonte=linha["fonte"],
                secao=linha["secao"],
                conteudo=linha["conteudo"],
                similaridade=float(linha["similaridade"]),
                nota_rrf=float(linha["nota_rrf"]),
                pos_palavras=linha.get("pos_palavras"),
                pos_sentido=linha.get("pos_sentido"),
            )
            for linha in linhas
        ]

    def contar(self, colecao: str = "producao") -> int:
        """Quantos trechos há na coleção (a publicável só enxerga a 'producao')."""
        resposta = self._pedir(
            "GET",
            "/rest/v1/trechos",
            params={"select": "id", "colecao": f"eq.{colecao}", "limit": "1"},
            headers={"Prefer": "count=exact"},
        )
        total = resposta.headers.get("content-range", "").rpartition("/")[2]
        if not total.isdigit():
            raise ErroBanco("O Supabase não informou quantos trechos existem.")
        return int(total)

    # ---------------------------------------- escrita (só a chave secreta)

    def gravar(self, linhas: Sequence[Mapping[str, Any]], lote: int = LOTE_GRAVACAO) -> int:
        """Grava trechos já com embedding. Cada linha tem colecao, fonte, secao, ordem, conteudo, embedding, modelo."""
        for linha in linhas:
            if linha.get("colecao") not in COLECOES:
                raise ErroBanco(f"Coleção inválida: {linha.get('colecao')!r}")
        for inicio in range(0, len(linhas), lote):
            pedaco = [{**item, "embedding": vetor_texto(item["embedding"])} for item in linhas[inicio : inicio + lote]]
            self._pedir("POST", "/rest/v1/trechos", json=pedaco, headers={"Prefer": "return=minimal"})
        return len(linhas)

    def limpar_teste(self) -> int:
        """Apaga a coleção 'teste'. Devolve quantos trechos saíram."""
        return int(self._rpc("limpar_teste"))

    def promover_teste(self) -> int:
        """'teste' vira 'producao' numa única transação. Devolve quantos trechos foram promovidos."""
        return int(self._rpc("promover_teste"))


def do_ambiente(nome_chave: str, ambiente: Mapping[str, str] | None = None) -> Banco:
    """Monta o Banco com SUPABASE_URL e a chave indicada (secreta ou publicável)."""
    ambiente = os.environ if ambiente is None else ambiente
    faltando = [n for n in ("SUPABASE_URL", nome_chave) if not ambiente.get(n, "").strip()]
    if faltando:
        raise ErroBanco(
            f"Faltam as variáveis {', '.join(faltando)}. No GitHub, cadastre-as em "
            "Settings → Secrets and variables → Actions."
        )
    return Banco(ambiente["SUPABASE_URL"], ambiente[nome_chave].strip())
