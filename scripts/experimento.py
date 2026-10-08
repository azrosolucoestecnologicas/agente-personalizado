"""TEMPORÁRIO (calibração da tarefa 5): compara variações de chunking e pesos numa só execução.

Só escreve na coleção "teste". Será removido depois da calibração.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import avaliar  # noqa: E402
import indexar  # noqa: E402

from agente import documentos  # noqa: E402
from agente.banco import do_ambiente  # noqa: E402
from agente.config import carregar_config  # noqa: E402
from agente.embeddings import EmbeddingsFastembed  # noqa: E402
from agente.perguntas import carregar  # noqa: E402

original = documentos.dividir_pasta


def com_titulo_do_documento(pasta=documentos.PASTA_PADRAO, tamanho_trecho=1500, sobreposicao=200):
    titulos = {}
    for doc in sorted(pasta.glob("*.md")):
        primeira = next(linha for linha in doc.read_text(encoding="utf-8").splitlines() if linha.startswith("# "))
        titulos[doc.name] = primeira[2:].strip()
    return [
        dataclasses.replace(t, conteudo=f"{titulos[t.fonte]} > {t.conteudo}")
        for t in original(pasta, tamanho_trecho, sobreposicao)
    ]


def main() -> int:
    base0 = carregar_config().base_conhecimento
    conjunto = carregar()
    banco = do_ambiente("SUPABASE_SECRET_KEY")
    gerador = EmbeddingsFastembed(base0.modelo_embedding)
    linhas = [
        "| Trecho | Contexto | Pesos (pal/sent) | hit@3 | MRR | Erros | Fora (máx) | Certos (mín) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for tamanho in (600, 900, 1200, 1500):
        for contexto in (False, True):
            indexar.dividir_pasta = com_titulo_do_documento if contexto else original
            base = dataclasses.replace(base0, tamanho_trecho=tamanho, sobreposicao=min(200, tamanho // 4))
            indexar.indexar(banco, gerador, base)
            for pp, ps in ((1.0, 1.0), (1.0, 0.0), (0.0, 1.0), (0.5, 1.0), (1.0, 0.5)):
                b = dataclasses.replace(base, peso_palavras=pp, peso_sentido=ps)
                rel = avaliar.avaliar(banco, gerador, conjunto, b)
                erros = ",".join(str(i) for i, r in enumerate(rel.respostas, 1) if not r.acertou)
                certos = [r.certo.similaridade for r in rel.respostas if r.acertou]
                fora = max((s for _, s in rel.fora), default=0)
                linhas.append(
                    f"| {tamanho} | {'título' if contexto else '—'} | {pp}/{ps} | {rel.hit_rate:.2f} | {rel.mrr:.3f} "
                    f"| {erros} | {fora:.3f} | {min(certos, default=0):.3f} |"
                )
            print("\n".join(linhas[-5:]), flush=True)
    texto = "## Experimento de calibração\n\n" + "\n".join(linhas)
    print(texto)
    avaliar.escrever_resumo_actions(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
