"""Ponto de entrada do Space: lê o config.yaml, monta a fila de IAs e abre o chat.

Rodar no computador:
    python app.py      (depois abra http://127.0.0.1:7860)
"""

import spaces  # precisa vir primeiro no hardware ZeroGPU

import logging
import sys

from agente.config import ErroConfig, carregar_config
from agente.interface import criar_app
from agente.provedores import criar_provedores
from agente.rag import criar_rag

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agente")


@spaces.GPU
def exigencia_zerogpu() -> None:
    """RF21: a ZeroGPU exige ao menos uma função com @spaces.GPU para iniciar.

    Nada aqui usa GPU: as IAs rodam nos provedores externos. Esta função
    nunca é chamada, então não gasta a sua cota de GPU. Fora da ZeroGPU,
    o decorador não faz nada.
    """


try:
    config = carregar_config()
except ErroConfig as erro:
    # RF1: configuração inválida -> o app não sobe e explica o que corrigir.
    print("O config.yaml tem problemas:\n" + "\n".join(erro.erros), file=sys.stderr)
    sys.exit(1)

provedores = criar_provedores(config)
if provedores:
    log.info("Fila de provedores: %s", " → ".join(f"{p.nome} ({p.modelo})" for p in provedores))
else:
    log.warning("Nenhuma chave de IA cadastrada: o chat vai explicar como cadastrar.")

# Parte 2: carrega o modelo de embedding e conta os trechos da produção (RF37).
# Sem os secrets do Supabase, o chat avisa que a base está indisponível.
rag = criar_rag(config.base_conhecimento)

demo, opcoes_launch = criar_app(config, provedores, rag)

if __name__ == "__main__":
    demo.launch(**opcoes_launch)
