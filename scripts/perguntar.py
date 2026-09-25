"""Faz UMA pergunta à IA pelo terminal, usando o config.yaml e as suas chaves.

Serve para testar os provedores antes de existir a tela do chat.
As chaves são lidas das variáveis de ambiente (nunca escreva a chave aqui!).

Uso:
    export OPENROUTER_API_KEY="..."        # e/ou ANTHROPIC_API_KEY, OPENAI_API_KEY
    python scripts/perguntar.py "O que é um pipeline de dados?"
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.config import ErroConfig, carregar_config  # noqa: E402
from agente.provedores import criar_provedores  # noqa: E402
from agente.roteador import responder  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('Uso: python scripts/perguntar.py "sua pergunta"')
        return 2
    logging.basicConfig(level=logging.INFO, format="   [log] %(message)s")
    try:
        config = carregar_config()
    except ErroConfig as erro:
        print("\n".join(erro.erros))
        return 1

    fila = criar_provedores(config)
    print("Fila de provedores:", " → ".join(f"{p.nome} ({p.modelo})" for p in fila) or "(nenhuma chave)")
    print("-" * 60)
    mostrado = ""
    for texto in responder(argv[1], [], config, fila):
        # 'texto' é acumulado: imprime só a parte nova, para aparecer palavra por palavra.
        if texto.startswith(mostrado):
            print(texto[len(mostrado) :], end="", flush=True)
        else:
            print("\n" + texto, end="", flush=True)
        mostrado = texto
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
