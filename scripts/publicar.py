"""Envia o app para o Space no Hugging Face e acompanha o build.

Usado pelo GitHub Actions (job "publicar"), só depois que todos os testes passam.

Variáveis de ambiente:
    HF_TOKEN   token do Hugging Face com permissão de escrita no Space (secret do GitHub)
    HF_SPACE   nome do Space; padrão: thiagoazro/agente-personalizado

Uso manual (raramente necessário):
    HF_TOKEN=hf_... python scripts/publicar.py
"""

from __future__ import annotations

import fnmatch
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SPACE_PADRAO = "thiagoazro/agente-personalizado"

# Só isto vai para o Space (spec, seção 3). Testes, scripts e .github ficam no GitHub.
ARQUIVOS_DO_APP = ["README.md", "app.py", "config.yaml", "requirements.txt", "assets/*", "agente/*"]
IGNORAR = ["*__pycache__*", "*.pyc", ".DS_Store"]

ESTAGIOS_OK = {"RUNNING"}
ESTAGIOS_ERRO = {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"}
ESTAGIOS_PARADO = {"STOPPED", "PAUSED", "SLEEPING"}


def escrever_resumo(texto: str) -> None:
    """Mostra o resultado na aba 'Summary' da execução do GitHub Actions."""
    print(texto)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")


def arquivos_para_publicar(raiz: Path = RAIZ) -> list[str]:
    """Lista (para conferência) os arquivos que serão enviados ao Space."""
    arquivos = []
    for caminho in sorted(raiz.rglob("*")):
        relativo = caminho.relative_to(raiz).as_posix()
        if not caminho.is_file() or any(fnmatch.fnmatch(relativo, p) for p in IGNORAR):
            continue
        if any(fnmatch.fnmatch(relativo, p) for p in ARQUIVOS_DO_APP):
            arquivos.append(relativo)
    return arquivos


def mensagem_do_commit() -> str:
    sha = os.environ.get("GITHUB_SHA", "")[:7]
    return f"Publicação automática do GitHub ({sha})" if sha else "Publicação manual"


def enviar(api, space: str, raiz: Path = RAIZ):
    """Envia os arquivos do app e apaga do Space os que não existem mais. Devolve o commit."""
    commit = api.upload_folder(
        repo_id=space,
        repo_type="space",
        folder_path=str(raiz),
        allow_patterns=ARQUIVOS_DO_APP,
        ignore_patterns=IGNORAR,
        delete_patterns=["*"],  # o .gitattributes do Space é sempre preservado
        commit_message=mensagem_do_commit(),
    )
    return commit


def aguardar_build(
    api,
    space: str,
    sha_esperado: str | None = None,
    limite_segundos: int = 15 * 60,
    intervalo: int = 15,
    espera_inicial: int = 20,
    dormir: Callable[[float], None] | None = None,
    agora: Callable[[], float] | None = None,
) -> tuple[bool, str]:
    """Acompanha o Space até ficar no ar. Devolve (sucesso, mensagem)."""
    dormir = dormir or time.sleep
    agora = agora or time.monotonic
    dormir(espera_inicial)  # dá tempo de o Hugging Face começar o novo build
    inicio = agora()
    estagio = "?"
    while agora() - inicio < limite_segundos:
        runtime = api.get_space_runtime(space)
        estagio = str(getattr(runtime.stage, "value", runtime.stage))
        sha_rodando = (getattr(runtime, "raw", None) or {}).get("sha")
        print(f"   Estado do Space: {estagio}", flush=True)
        # Logo após o envio, o Space ainda pode estar rodando a versão ANTIGA.
        versao_antiga = bool(sha_esperado and sha_rodando and sha_rodando != sha_esperado)
        if estagio in ESTAGIOS_OK and not versao_antiga:
            return True, "no ar (RUNNING)"
        if estagio in ESTAGIOS_ERRO:
            return False, f"o Space parou com {estagio}"
        if estagio in ESTAGIOS_PARADO:
            return True, f"publicado, mas o Space está {estagio}: ele acorda na próxima visita"
        dormir(intervalo)
    return True, f"publicado, mas o build ainda não terminou em {limite_segundos // 60} min (último estado: {estagio})"


def main() -> int:
    token = os.environ.get("HF_TOKEN", "").strip()
    space = os.environ.get("HF_SPACE", "").strip() or SPACE_PADRAO
    link_space = f"https://huggingface.co/spaces/{space}"
    if not token:
        escrever_resumo(
            "## ❌ Publicação não feita: falta o secret HF_TOKEN\n\n"
            "No GitHub: Settings → Secrets and variables → Actions → New repository secret → "
            "nome `HF_TOKEN`, valor = token do Hugging Face com permissão de escrita no Space."
        )
        return 1

    from huggingface_hub import HfApi
    from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

    api = HfApi(token=token)
    print(f"Enviando para {space}:")
    for arquivo in arquivos_para_publicar():
        print(f"   {arquivo}")
    try:
        commit = enviar(api, space)
    except RepositoryNotFoundError:
        escrever_resumo(
            f"## ❌ Space `{space}` não encontrado\n\n"
            "Crie o Space no Hugging Face (SDK Gradio) ou confira o nome. "
            "Se ele existe, o HF_TOKEN pode não ter acesso a ele."
        )
        return 1
    except HfHubHTTPError as erro:
        status = getattr(erro.response, "status_code", "?")
        dica = (
            "O HF_TOKEN está inválido, expirado ou sem permissão de escrita neste Space. Gere um novo token."
            if status in (401, 403)
            else "Tente rodar o job de novo em alguns minutos."
        )
        escrever_resumo(f"## ❌ O Hugging Face recusou o envio ({status})\n\n{dica}")
        return 1

    link_commit = getattr(commit, "commit_url", "")
    print(f"Enviado: {link_commit}\nAcompanhando o build…")
    sucesso, detalhe = aguardar_build(api, space, sha_esperado=getattr(commit, "oid", None))
    if sucesso:
        escrever_resumo(f"## ✅ Publicado: {detalhe}\n\n- Chat: {link_space}\n- Alteração: {link_commit}")
        return 0
    escrever_resumo(
        f"## ❌ Arquivos enviados, mas {detalhe}\n\n"
        f"Veja o log em {link_space} (aba **Logs**). Corrija no GitHub e salve de novo."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
