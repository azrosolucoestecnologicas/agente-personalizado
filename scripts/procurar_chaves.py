"""Procura chaves de API esquecidas nos arquivos do projeto (verificação T8).

Uso:
    python scripts/procurar_chaves.py            # varre o projeto inteiro
    python scripts/procurar_chaves.py outra/pasta

O que é verificado:
  - todos os arquivos que vão (ou já foram) para o Git;
  - nenhum arquivo .env pode estar no repositório.

Sai com código 0 se estiver tudo limpo e 1 se achar algo
(o GitHub Actions usa esse código para barrar a publicação).
A chave encontrada NUNCA é mostrada inteira, só o começo dela.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.segredos import procurar_em_texto  # noqa: E402

TAMANHO_MAX = 2 * 1024 * 1024  # arquivos maiores que 2 MB são pulados (imagens, etc.)
PASTAS_IGNORADAS = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".ruff_cache", ".gradio", "node_modules"}


def eh_arquivo_env(caminho: Path) -> bool:
    """.env, .env.local, producao.env... (mesmas regras do .gitignore)."""
    nome = caminho.name
    return nome == ".env" or nome.startswith(".env.") or nome.endswith(".env")


def listar_arquivos(pasta: Path) -> list[Path]:
    """Arquivos que o Git versiona ou versionaria (respeita o .gitignore).

    Se a pasta não for um repositório Git, varre tudo.
    """
    try:
        saida = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=pasta,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        return sorted(pasta / nome for nome in saida.split("\0") if nome and (pasta / nome).is_file())
    except (OSError, subprocess.CalledProcessError):
        arquivos = []
        for raiz, pastas, nomes in os.walk(pasta):
            pastas[:] = [p for p in pastas if p not in PASTAS_IGNORADAS]
            arquivos += [Path(raiz) / n for n in nomes]
        return sorted(arquivos)


def ler_texto(caminho: Path) -> str | None:
    """Devolve o conteúdo, ou None para arquivos binários ou grandes demais."""
    if caminho.stat().st_size > TAMANHO_MAX:
        return None
    dados = caminho.read_bytes()
    if b"\0" in dados[:8192]:
        return None  # binário (imagem, etc.)
    return dados.decode("utf-8", errors="replace")


def procurar(pasta: Path) -> list[str]:
    """Devolve uma lista de problemas no formato 'arquivo:linha: descrição'."""
    problemas = []
    for arquivo in listar_arquivos(pasta):
        relativo = arquivo.relative_to(pasta).as_posix()
        if eh_arquivo_env(arquivo):
            problemas.append(f"{relativo}: arquivo .env não pode ir para o repositório (pode conter chaves).")
            continue
        texto = ler_texto(arquivo)
        if texto is None:
            continue
        for numero, linha in enumerate(texto.splitlines(), start=1):
            for achado in procurar_em_texto(linha):
                problemas.append(f"{relativo}:{numero}: {achado.tipo} encontrada ({achado.trecho}).")
    return problemas


def escrever_resumo_actions(texto: str) -> None:
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")


COMO_RESOLVER = """Como resolver:
  1. Apague a chave do arquivo (ou remova o arquivo .env do repositório).
  2. REVOGUE a chave no site do provedor: ela já pode ter ficado no histórico do Git.
  3. Crie uma chave nova e cadastre-a SÓ nos secrets do Space no Hugging Face.
O site publicado continua como estava."""


def main(argv: list[str]) -> int:
    pasta = Path(argv[1]).resolve() if len(argv) > 1 else RAIZ
    problemas = procurar(pasta)
    if not problemas:
        print("✅ Nenhuma chave de API encontrada nos arquivos do projeto.")
        escrever_resumo_actions("## ✅ Nenhuma chave de API encontrada")
        return 0

    print(f"❌ Encontrei {len(problemas)} possível(is) chave(s) de API no projeto:\n")
    for problema in problemas:
        print(f"  ❌ {problema}")
    print("\n" + COMO_RESOLVER)
    escrever_resumo_actions(
        f"## ❌ {len(problemas)} possível(is) chave(s) de API no projeto\n\n"
        + "\n".join(f"- `{p}`" for p in problemas)
        + "\n\n```\n"
        + COMO_RESOLVER
        + "\n```"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
