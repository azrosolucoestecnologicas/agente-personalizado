"""Confere a pasta documentos/ (verificação T19) e explica os erros em português.

Uso:
    python scripts/validar_documentos.py

Sai com código 0 se estiver tudo certo e 1 se houver erro
(o GitHub Actions usa esse código para barrar a publicação).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.documentos import PASTA_PADRAO, ler_titulos, validar_pasta  # noqa: E402


def escrever_resumo_actions(texto: str) -> None:
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")


def main(argv: list[str]) -> int:
    pasta = Path(argv[1]) if len(argv) > 1 else PASTA_PADRAO
    erros = validar_pasta(pasta)
    if erros:
        print(f"❌ A pasta documentos/ tem {len(erros)} problema(s):\n")
        for erro in erros:
            print(f"  {erro}")
        print("\nCorrija os itens acima e salve de novo. O site publicado continua como estava.")
        escrever_resumo_actions(f"## ❌ documentos/: {len(erros)} problema(s)\n\n" + "\n".join(f"- {e}" for e in erros))
        return 1
    linhas = []
    for documento in sorted(pasta.glob("*.md")):
        titulos = ler_titulos(documento.read_text(encoding="utf-8"))
        secoes = sum(1 for t in titulos if t.nivel == 2)
        linhas.append(f"   {documento.name}: {secoes} seções, {documento.stat().st_size // 1024} KB")
    mensagem = "✅ A pasta documentos/ está correta.\n" + "\n".join(linhas)
    print(mensagem)
    escrever_resumo_actions(f"## ✅ documentos/ está correta\n\n```\n{mensagem}\n```")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
