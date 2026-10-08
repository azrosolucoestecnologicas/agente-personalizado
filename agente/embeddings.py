"""Embeddings: transforma texto em 768 números (spec da Parte 2, seção 2).

Usa a fastembed (ONNX, sem PyTorch). O e5-base não vem pronto na lista da
fastembed, então é registrado como modelo próprio, apontando para o arquivo
onnx/model.onnx do repositório oficial no Hugging Face.

O MESMO modelo roda nos dois lados: no GitHub Actions (trechos) e no Space
(pergunta). O e5 exige prefixos: "passage: " nos trechos e "query: " nas
perguntas. Os vetores saem normalizados (tamanho 1), como a busca espera.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from agente.config import DIMENSAO_EMBEDDING, MODELOS_EMBEDDING

# Modelo -> (prefixo do trecho, prefixo da pergunta). Modelos fora daqui não usam prefixo.
PREFIXOS = {
    "intfloat/multilingual-e5-base": ("passage: ", "query: "),
}
# Modelos que a fastembed não traz prontos: registrados na primeira vez que forem usados.
MODELOS_PROPRIOS = {
    "intfloat/multilingual-e5-base": "onnx/model.onnx",
}
LOTE = 32  # trechos por vez: equilibra memória e velocidade


class ErroEmbedding(Exception):
    """O modelo de embedding não pôde ser carregado ou usado."""


class GeradorEmbeddings(Protocol):
    """O que o resto do app usa. Os testes trocam por um gerador falso."""

    modelo: str

    def trechos(self, textos: Sequence[str]) -> list[list[float]]: ...

    def pergunta(self, texto: str) -> list[float]: ...


def com_prefixo(modelo: str, textos: Iterable[str], tipo: str) -> list[str]:
    """Acrescenta "passage: " (tipo="trecho") ou "query: " (tipo="pergunta") quando o modelo pede."""
    trecho, pergunta = PREFIXOS.get(modelo, ("", ""))
    prefixo = trecho if tipo == "trecho" else pergunta
    return [prefixo + t for t in textos]


def _registrar(modelo: str) -> None:
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    if any(m["model"] == modelo for m in TextEmbedding.list_supported_models()):
        return
    TextEmbedding.add_custom_model(
        model=modelo,
        pooling=PoolingType.MEAN,
        normalization=True,
        sources=ModelSource(hf=modelo),
        dim=MODELOS_EMBEDDING[modelo],
        model_file=MODELOS_PROPRIOS[modelo],
    )


class EmbeddingsFastembed:
    """Gera os vetores com a fastembed. Na primeira vez, baixa o modelo (~1,1 GB)."""

    def __init__(self, modelo: str, pasta_cache: str | None = None):
        if modelo not in MODELOS_EMBEDDING:
            raise ErroEmbedding(f'O modelo "{modelo}" não é aceito. Use um destes: {", ".join(MODELOS_EMBEDDING)}.')
        self.modelo = modelo
        try:
            from fastembed import TextEmbedding

            if modelo in MODELOS_PROPRIOS:
                _registrar(modelo)
            # pasta_cache=None: a fastembed usa a variável FASTEMBED_CACHE_PATH, se existir.
            self._motor = TextEmbedding(model_name=modelo, cache_dir=pasta_cache)
        except ErroEmbedding:
            raise
        except Exception as erro:  # rede, disco cheio, arquivo corrompido...
            raise ErroEmbedding(f"Não consegui carregar o modelo {modelo}: {type(erro).__name__}: {erro}") from erro

    def _gerar(self, textos: list[str]) -> list[list[float]]:
        vetores = [v.tolist() for v in self._motor.embed(textos, batch_size=LOTE)]
        for vetor in vetores:
            if len(vetor) != DIMENSAO_EMBEDDING:
                raise ErroEmbedding(
                    f"O modelo {self.modelo} gerou {len(vetor)} números, mas o banco espera {DIMENSAO_EMBEDDING}."
                )
        return vetores

    def trechos(self, textos: Sequence[str]) -> list[list[float]]:
        return self._gerar(com_prefixo(self.modelo, textos, "trecho"))

    def pergunta(self, texto: str) -> list[float]:
        return self._gerar(com_prefixo(self.modelo, [texto], "pergunta"))[0]
