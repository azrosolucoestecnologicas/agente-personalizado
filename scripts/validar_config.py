"""Valida o config.yaml e explica os erros em português.

Uso:
    python scripts/validar_config.py              # valida o config.yaml da raiz
    python scripts/validar_config.py outro.yaml   # valida outro arquivo

Sai com código 0 se estiver tudo certo e 1 se houver erro
(o GitHub Actions usa esse código para barrar a publicação).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.config import ARQUIVO_PADRAO, ErroConfig, carregar_config  # noqa: E402


def escrever_resumo_actions(texto: str) -> None:
    """No GitHub Actions, mostra o resultado na aba 'Summary' da execução."""
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")


def main(argv: list[str]) -> int:
    caminho = Path(argv[1]) if len(argv) > 1 else ARQUIVO_PADRAO
    try:
        config = carregar_config(caminho)
    except ErroConfig as erro:
        titulo = f"## ❌ {caminho.name} tem {len(erro.erros)} problema(s)"
        print(titulo.removeprefix("## ") + ":\n")
        for linha in erro.erros:
            print(f"  {linha}")
        print("\nCorrija os itens acima e salve de novo. O site publicado continua como estava.")
        escrever_resumo_actions(titulo + "\n\n" + "\n".join(f"- {linha}" for linha in erro.erros))
        return 1

    provedores = " → ".join(f"{p.nome} ({p.modelo})" for p in config.provedores)
    mensagem = (
        f"✅ {caminho.name} está correto.\n"
        f"   Assistente: {config.nome}\n"
        f"   Cores: {config.cor_principal} → {config.cor_secundaria}\n"
        f"   Logo: {config.logo.relative_to(caminho.resolve().parent).as_posix()} ({config.logo_altura}px)\n"
        f"   Provedores: {provedores}\n"
        f"   Exemplos: {len(config.exemplos)}"
    )
    print(mensagem)
    escrever_resumo_actions(f"## ✅ {caminho.name} está correto\n\n```\n{mensagem}\n```")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
