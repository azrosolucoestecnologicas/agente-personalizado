"""Confere o perguntas_teste.yaml (verificação T21), sem rede.

Uso:
    python scripts/validar_perguntas.py

Sai com código 0 se estiver tudo certo e 1 se houver erro.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.perguntas import ErroPerguntas, carregar  # noqa: E402


def escrever_resumo_actions(texto: str) -> None:
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")


def main() -> int:
    try:
        conjunto = carregar()
    except ErroPerguntas as erro:
        print(f"❌ perguntas_teste.yaml tem {len(erro.erros)} problema(s):\n")
        for linha in erro.erros:
            print(f"  {linha}")
        print("\nCorrija os itens acima e salve de novo. O site publicado continua como estava.")
        escrever_resumo_actions(
            f"## ❌ perguntas_teste.yaml: {len(erro.erros)} problema(s)\n\n" + "\n".join(f"- {e}" for e in erro.erros)
        )
        return 1
    por_fonte = Counter(p.fonte_esperada for p in conjunto.perguntas)
    linhas = "\n".join(f"   {fonte}: {n} pergunta(s)" for fonte, n in sorted(por_fonte.items()))
    mensagem = (
        f"✅ perguntas_teste.yaml está correto: {len(conjunto.perguntas)} perguntas, "
        f"hit rate@{conjunto.top_k} mínimo de {conjunto.limiar_hit_rate:.2f}.\n{linhas}"
    )
    print(mensagem)
    escrever_resumo_actions(f"## ✅ perguntas_teste.yaml está correto\n\n```\n{mensagem}\n```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
