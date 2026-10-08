"""Monta a coleção "teste" no Supabase a partir da pasta documentos/ (RF27 e RF28).

Uso (no GitHub Actions, com os secrets SUPABASE_URL e SUPABASE_SECRET_KEY):
    python scripts/indexar.py             # apaga e regrava a coleção "teste"
    python scripts/indexar.py --promover  # "teste" vira "producao" (uma transação)

Sem --promover, este script NUNCA escreve na "producao": o assistente no ar
continua com o índice anterior até a avaliação passar.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.banco import Banco, ErroBanco, do_ambiente  # noqa: E402
from agente.config import BaseConhecimento, ErroConfig, carregar_config  # noqa: E402
from agente.documentos import PASTA_PADRAO, dividir_pasta  # noqa: E402
from agente.embeddings import ErroEmbedding, GeradorEmbeddings  # noqa: E402

CHAVE = "SUPABASE_SECRET_KEY"


def escrever_resumo_actions(texto: str) -> None:
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")


def indexar(banco: Banco, gerador: GeradorEmbeddings, base: BaseConhecimento, pasta: Path = PASTA_PADRAO) -> str:
    """Divide, gera os vetores e regrava a coleção "teste". Devolve o relatório em Markdown."""
    inicio = time.monotonic()
    trechos = dividir_pasta(pasta, base.tamanho_trecho, base.sobreposicao)
    if not trechos:
        raise ErroBanco("A pasta documentos/ não gerou nenhum trecho: nada a indexar.")
    print(f"→ {len(trechos)} trechos. Gerando os vetores com {gerador.modelo}...", flush=True)
    # Vetores ANTES de apagar: se o modelo falhar, a coleção "teste" fica como estava.
    vetores = gerador.trechos([t.conteudo for t in trechos])

    apagados = banco.limpar_teste()
    print(f"→ Coleção teste: {apagados} trechos antigos apagados. Gravando os novos...", flush=True)
    banco.gravar(
        [
            {
                "colecao": "teste",  # nunca "producao": quem promove é o --promover
                "fonte": t.fonte,
                "secao": t.secao,
                "ordem": t.ordem,
                "conteudo": t.conteudo,
                "embedding": v,
                "modelo": gerador.modelo,
            }
            for t, v in zip(trechos, vetores, strict=True)
        ]
    )
    no_banco = banco.contar("teste")
    if no_banco != len(trechos):
        raise ErroBanco(f"Gravei {len(trechos)} trechos, mas a coleção teste tem {no_banco}. Rode de novo.")

    por_fonte = Counter(t.fonte for t in trechos)
    linhas = "\n".join(f"| {fonte} | {n} |" for fonte, n in sorted(por_fonte.items()))
    return (
        f"## ✅ Coleção teste indexada: {len(trechos)} trechos\n\n"
        f"Modelo `{gerador.modelo}`, trechos de até {base.tamanho_trecho} caracteres "
        f"(sobreposição {base.sobreposicao}), em {time.monotonic() - inicio:.0f} s.\n\n"
        f"| Documento | Trechos |\n|---|---|\n{linhas}\n"
    )


def promover(banco: Banco) -> str:
    n = banco.promover_teste()
    return f"## ✅ Promoção: a coleção producao agora tem {n} trechos\n\nO assistente no ar já consulta o índice novo."


def main(argv: list[str] | None = None, gerador: GeradorEmbeddings | None = None, banco: Banco | None = None) -> int:
    parser = argparse.ArgumentParser(description="Indexa documentos/ na coleção teste do Supabase.")
    parser.add_argument("--promover", action="store_true", help='troca a "producao" pela "teste" (uma transação)')
    args = parser.parse_args(argv)
    try:
        base = carregar_config().base_conhecimento
        banco = banco or do_ambiente(CHAVE)
        if args.promover:
            relatorio = promover(banco)
        else:
            if gerador is None:
                from agente.embeddings import EmbeddingsFastembed

                print(f"→ Carregando o modelo {base.modelo_embedding} (na primeira vez, baixa ~470 MB)...", flush=True)
                gerador = EmbeddingsFastembed(base.modelo_embedding)
            relatorio = indexar(banco, gerador, base)
    except (ErroConfig, ErroBanco, ErroEmbedding) as erro:
        acao = "promover" if args.promover else "indexar"
        print(f"❌ Não consegui {acao}: {erro}")
        print("A coleção producao não foi alterada: o assistente no ar continua como estava.")
        escrever_resumo_actions(f"## ❌ Não consegui {acao}\n\n{erro}\n\nA coleção producao não foi alterada.")
        return 1
    print(relatorio)
    escrever_resumo_actions(relatorio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
