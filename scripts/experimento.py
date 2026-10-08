"""TEMPORÁRIO (calibração da tarefa 5): compara modelos de embedding e um reranker.

A busca por palavras vem do banco de verdade (coleção "teste"); a busca por
sentido de cada modelo é calculada em memória, e as duas são fundidas por RRF
como na função buscar_hibrido. Só escreve na coleção "teste". Será removido.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import indexar  # noqa: E402

from agente.banco import do_ambiente  # noqa: E402
from agente.config import carregar_config  # noqa: E402
from agente.documentos import dividir_pasta  # noqa: E402
from agente.embeddings import EmbeddingsFastembed  # noqa: E402
from agente.perguntas import carregar, secao_confere  # noqa: E402

MODELOS = [
    # (nome, prefixo trecho, prefixo pergunta, arquivo onnx próprio ou None, dimensão)
    ("intfloat/multilingual-e5-small", "passage: ", "query: ", "onnx/model.onnx", 384),
    ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "", "", None, 384),
    ("intfloat/multilingual-e5-base", "passage: ", "query: ", "onnx/model.onnx", 768),
    ("sentence-transformers/paraphrase-multilingual-mpnet-base-v2", "", "", None, 768),
    ("intfloat/multilingual-e5-large", "passage: ", "query: ", None, 1024),
]
RERANKER = "jinaai/jina-reranker-v2-base-multilingual"
K, CANDIDATOS, TOP = 60, 20, 3


def motor(nome, arquivo, dim):
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    if arquivo and not any(m["model"] == nome for m in TextEmbedding.list_supported_models()):
        TextEmbedding.add_custom_model(
            model=nome,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=nome),
            dim=dim,
            model_file=arquivo,
        )
    return TextEmbedding(model_name=nome)


def normalizar(m):
    m = np.asarray(m, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def rrf(lista_palavras, lista_sentido):
    nota = {}
    for pos, i in enumerate(lista_palavras, 1):
        nota[i] = nota.get(i, 0) + 1 / (K + pos)
    for pos, i in enumerate(lista_sentido, 1):
        nota[i] = nota.get(i, 0) + 1 / (K + pos)
    return sorted(nota, key=lambda i: (-nota[i], i))


def main() -> int:
    base = carregar_config().base_conhecimento
    conjunto = carregar()
    banco = do_ambiente("SUPABASE_SECRET_KEY")
    e5 = EmbeddingsFastembed(base.modelo_embedding)
    indexar.indexar(banco, e5, base)  # coleção teste com a configuração atual

    trechos = dividir_pasta(tamanho_trecho=base.tamanho_trecho, sobreposicao=base.sobreposicao)
    indice = {t.conteudo: i for i, t in enumerate(trechos)}
    perguntas = [p.pergunta for p in conjunto.perguntas]
    todas = perguntas + conjunto.fora_do_material

    # Busca por palavras: do banco (independe do modelo).
    palavras = []
    for texto in todas:
        res = banco.buscar(texto, e5.pergunta(texto), quantidade=CANDIDATOS, peso_sentido=0.0, colecao="teste")
        palavras.append([indice[r.conteudo] for r in res if r.pos_palavras is not None])

    def certo(n, i):
        p = conjunto.perguntas[n]
        return trechos[i].fonte == p.fonte_esperada and secao_confere(trechos[i].secao, p.secao_esperada)

    def medir(rankings):
        acertos, rr, erros = 0, 0.0, []
        for n in range(len(perguntas)):
            pos = next((k for k, i in enumerate(rankings[n][:TOP], 1) if certo(n, i)), None)
            if pos:
                acertos, rr = acertos + 1, rr + 1 / pos
            else:
                erros.append(str(n + 1))
        return acertos / len(perguntas), rr / len(perguntas), ",".join(erros) or "—"

    linhas = [
        "| Pesos (pal/sent) | hit@3 | MRR | Erros | Certos sim mín | Fora sim (cada) |",
        "|---|---|---|---|---|---|",
    ]
    nome, pt, pq, arquivo, dim = MODELOS[2]  # e5-base
    m = motor(nome, arquivo, dim)
    mt = normalizar(list(m.embed([pt + t.conteudo for t in trechos], batch_size=16)))
    mq = normalizar(list(m.embed([pq + q for q in todas])))
    sims = mq @ mt.T
    sentido = [list(np.argsort(-sims[n], kind="stable")[:CANDIDATOS]) for n in range(len(todas))]
    fora = [float(sims[len(perguntas) + j].max()) for j in range(len(conjunto.fora_do_material))]
    for pp in (1.0, 0.7, 0.5, 0.3, 0.2, 0.0):
        hibrida = []
        for n in range(len(todas)):
            nota = {}
            for pos, i in enumerate(palavras[n], 1):
                nota[i] = nota.get(i, 0) + pp / (K + pos)
            for pos, i in enumerate(sentido[n], 1):
                nota[i] = nota.get(i, 0) + 1 / (K + pos)
            hibrida.append(sorted(nota, key=lambda i: (-nota[i], i)))
        h, mrr, erros = medir(hibrida)
        certos = [float(sims[n, i]) for n in range(len(perguntas)) for i in hibrida[n][:TOP] if certo(n, i)]
        linhas.append(
            f"| {pp}/1.0 | {h:.2f} | {mrr:.3f} | {erros} | {min(certos, default=0):.3f} | "
            + ", ".join(f"{s:.3f}" for s in fora)
            + " |"
        )
        print(linhas[-1], flush=True)
    # Similaridade do trecho certo de cada pergunta (melhor posição) e do 1º colocado
    for n, p in enumerate(conjunto.perguntas):
        melhor = next((i for i in sentido[n] if certo(n, i)), None)
        sc = f"{sims[n, melhor]:.3f}" if melhor is not None else "—"
        linhas.append(f"| P{n + 1} | certo {sc} | 1º {sims[n, sentido[n][0]]:.3f} | | | |")

    texto = "## Experimento: modelos e reranker\n\n" + "\n".join(linhas)
    print(texto)
    resumo = __import__("os").environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
