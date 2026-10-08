"""Mostra como os documentos são divididos em trechos (antes de ir para o banco).

Uso:
    python scripts/mostrar_trechos.py                      # resumo de todos os trechos
    python scripts/mostrar_trechos.py --completo           # com o texto inteiro de cada trecho
    python scripts/mostrar_trechos.py --filtro "segredos"  # só trechos cuja seção contém o texto

Usa o tamanho_trecho e a sobreposicao do config.yaml.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.config import carregar_config  # noqa: E402
from agente.documentos import dividir_pasta  # noqa: E402
from agente.perguntas import normalizar  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Mostra os trechos gerados a partir de documentos/.")
    parser.add_argument("--completo", action="store_true", help="mostra o texto inteiro de cada trecho")
    parser.add_argument("--filtro", default="", help="só trechos cuja seção contém este texto")
    args = parser.parse_args(argv)

    base = carregar_config().base_conhecimento
    trechos = dividir_pasta(tamanho_trecho=base.tamanho_trecho, sobreposicao=base.sobreposicao)
    if args.filtro:
        trechos = [t for t in trechos if normalizar(args.filtro) in normalizar(t.secao)]
    if not trechos:
        print("Nenhum trecho encontrado.")
        return 1

    tamanhos = [len(t.conteudo) for t in trechos]
    por_fonte = Counter(t.fonte for t in trechos)
    print(f"Trechos: {len(trechos)} (tamanho_trecho {base.tamanho_trecho}, sobreposição {base.sobreposicao})")
    for fonte, n in sorted(por_fonte.items()):
        print(f"   {fonte}: {n}")
    print(
        f"Tamanho: mínimo {min(tamanhos)}, média {statistics.mean(tamanhos):.0f}, máximo {max(tamanhos)} caracteres\n"
    )

    for t in trechos:
        print(f"[{t.fonte} #{t.ordem}] {t.secao}  ({len(t.conteudo)} caracteres)")
        if args.completo:
            print("-" * 72)
            print(t.conteudo)
            print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
