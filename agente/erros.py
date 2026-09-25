"""Traduz erros técnicos dos provedores para português, sem vazar chaves."""

from __future__ import annotations

from agente.segredos import ocultar_chaves


class FalhaProvedor(Exception):
    """Um provedor não conseguiu responder. `motivo` já está em português."""

    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


def _mensagem_original(erro: BaseException) -> str:
    return str(getattr(erro, "message", None) or erro).lower()


def traduzir(erro: BaseException, tempo_limite: int | None = None, chaves: tuple[str, ...] = ()) -> str:
    """Explica o erro em português, com o código HTTP quando houver.

    Funciona com as exceções dos SDKs anthropic e openai (que têm `status_code`)
    e com erros de rede/tempo do Python.
    """
    if isinstance(erro, FalhaProvedor):
        return ocultar_chaves(erro.motivo, chaves)

    nome_classe = type(erro).__name__
    status = getattr(erro, "status_code", None)
    texto = _mensagem_original(erro)

    if isinstance(erro, TimeoutError) or "Timeout" in nome_classe or status == 408:
        espera = f" (mais de {tempo_limite} s)" if tempo_limite else ""
        motivo = f"demorou demais para responder{espera}"
    elif isinstance(erro, ConnectionError) or "Connection" in nome_classe:
        motivo = "não foi possível conectar ao provedor (rede ou serviço fora do ar)"
    elif status == 401:
        motivo = "chave inválida ou revogada (401)"
    elif status == 402 or (status in (400, 403) and ("credit" in texto or "billing" in texto or "quota" in texto)):
        motivo = f"sem crédito na conta ({status})"
    elif status == 403:
        motivo = "chave sem permissão para este modelo (403)"
    elif status == 404:
        motivo = "modelo não encontrado: confira o ID no config.yaml (404)"
    elif status == 429:
        motivo = "limite de uso atingido; tente mais tarde (429)"
    elif status == 529 or "overloaded" in texto:
        motivo = f"provedor sobrecarregado ({status or 'sem código'})"
    elif isinstance(status, int) and status >= 500:
        motivo = f"provedor fora do ar ou instável ({status})"
    elif status == 400:
        motivo = "o provedor recusou o pedido (400); confira o modelo e os parâmetros no config.yaml"
    elif isinstance(status, int):
        motivo = f"erro do provedor ({status})"
    else:
        motivo = f"erro inesperado ({nome_classe})"
    return ocultar_chaves(motivo, chaves)


def recusou_parametro(erro: BaseException, parametro: str) -> bool:
    """True se o provedor recusou o pedido (400) por causa de um parâmetro específico.

    Ex.: modelos mais novos não aceitam 'temperature'.
    """
    return getattr(erro, "status_code", None) == 400 and parametro in _mensagem_original(erro)
