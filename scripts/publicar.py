"""Envia o app para o Space no Hugging Face e acompanha o build.

Usado pelo GitHub Actions (job "publicar"), só depois que todos os testes passam.

Variáveis de ambiente:
    HF_TOKEN   token do Hugging Face com permissão de escrita no Space (secret do GitHub)
    HF_SPACE   nome do Space; padrão: thiagoazro/agente-personalizado

Uso manual (raramente necessário):
    HF_TOKEN=hf_... python scripts/publicar.py              # confere e publica
    HF_TOKEN=hf_... python scripts/publicar.py --conferir   # só confere a configuração
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
# documentos/ vai como referência pública: o Space lê o material do banco, não dos arquivos.
ARQUIVOS_DO_APP = ["README.md", "app.py", "config.yaml", "requirements.txt", "assets/*", "agente/*", "documentos/*"]
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


VARIAVEIS_DE_CHAVE = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")
# Parte 2: o Space lê a base com a chave PUBLICÁVEL. A secreta (grava e promove) fica só no GitHub.
SUPABASE_NO_SPACE = ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY")
SUPABASE_PROIBIDA = "SUPABASE_SECRET_KEY"


def _explicar_erro_http(erro, space: str) -> str:
    from huggingface_hub.errors import RepositoryNotFoundError

    if isinstance(erro, RepositoryNotFoundError):
        return (
            f"Space `{space}` não encontrado, ou o HF_TOKEN não tem acesso a ele. "
            "Crie o Space (SDK Gradio) ou confira o nome e as permissões do token."
        )
    status = getattr(getattr(erro, "response", None), "status_code", "?")
    if status == 401:
        return "HF_TOKEN inválido ou expirado (401). Gere um novo token e atualize o secret no GitHub."
    if status == 403:
        return "O HF_TOKEN não tem permissão de ESCRITA neste Space (403). Gere um token com escrita."
    return f"O Hugging Face respondeu com erro ({status}). Tente de novo em alguns minutos."


def conferir(api, space: str, base_ativa: bool = True) -> tuple[list[str], list[str], list[str]]:
    """Confere a configuração manual (spec 7.2 e, na Parte 2, os secrets do Supabase).

    Devolve (erros, avisos, itens ok).

    Só lê NOMES de secrets; os valores nunca podem ser lidos.
    """
    from huggingface_hub.errors import HfHubHTTPError

    erros: list[str] = []
    avisos: list[str] = []
    ok: list[str] = []
    try:
        api.auth_check(space, repo_type="space", write=True)
        ok.append(f"Space `{space}` existe e o HF_TOKEN tem permissão de escrita")
    except HfHubHTTPError as erro:
        return [_explicar_erro_http(erro, space)], avisos, ok

    info = api.space_info(space)
    if info.sdk == "gradio":
        ok.append("SDK do Space: Gradio")
    else:
        erros.append(f"O Space foi criado com o SDK '{info.sdk}'. Ele precisa ser Gradio: crie o Space de novo.")

    runtime = getattr(info, "runtime", None)
    hardware = str(getattr(runtime, "requested_hardware", None) or getattr(runtime, "hardware", None) or "")
    if "zero" in hardware:
        ok.append(f"Hardware: ZeroGPU ({hardware})")
    else:
        avisos.append(
            f"Hardware atual: '{hardware or 'ainda não definido'}'. Para ZeroGPU: Settings → Space hardware "
            "(exige conta PRO). O app funciona igual em CPU."
        )

    try:
        secrets = set(api.get_space_secrets(space))
        variaveis = set(api.get_space_variables(space))
    except HfHubHTTPError:
        avisos.append("Não consegui listar os secrets do Space; confira à mão em Settings → Variables and secrets.")
        return erros, avisos, ok

    expostas = sorted(variaveis & set(VARIAVEIS_DE_CHAVE))
    if expostas:
        erros.append(
            f"{', '.join(expostas)} foi cadastrada como VARIABLE (fica visível para todos!). "
            "Apague-a, REVOGUE a chave no provedor e cadastre uma nova como SECRET."
        )
    presentes = [nome for nome in VARIAVEIS_DE_CHAVE if nome in secrets]
    if presentes:
        ok.append(f"Chaves de IA cadastradas como secret: {', '.join(presentes)}")
    elif not expostas:
        avisos.append(
            "Nenhuma chave de IA nos secrets do Space: o chat vai abrir, mas só vai pedir para cadastrar "
            "OPENROUTER_API_KEY, ANTHROPIC_API_KEY ou OPENAI_API_KEY."
        )
    if base_ativa:
        _conferir_supabase(secrets, variaveis, erros, ok)
    return erros, avisos, ok


def _conferir_supabase(secrets: set[str], variaveis: set[str], erros: list[str], ok: list[str]) -> None:
    """RF39 e RF40: no Space, só a URL e a chave publicável; a secreta, nunca."""
    if SUPABASE_PROIBIDA in secrets | variaveis:
        erros.append(
            f"{SUPABASE_PROIBIDA} está cadastrada no Space. Ela grava e apaga a base: fica SÓ no GitHub. "
            "Apague-a do Space e gere outra no Supabase (Project Settings → API Keys), depois atualize o GitHub."
        )
    faltando = [nome for nome in SUPABASE_NO_SPACE if nome not in secrets | variaveis]
    if faltando:
        erros.append(
            f"Falta no Space: {', '.join(faltando)} (Settings → Variables and secrets → New secret). "
            "Sem isso, o chat responde que a base de conhecimento está indisponível."
        )
    else:
        ok.append("Supabase no Space: SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY (só leitura)")


def _base_ativa() -> bool:
    """A base de conhecimento está ligada no config.yaml? (se o config não abrir, os testes já acusaram)"""
    sys.path.insert(0, str(RAIZ))
    from agente.config import ErroConfig, carregar_config

    try:
        return carregar_config().base_conhecimento.ativa
    except ErroConfig:
        return True


def relatorio(erros: list[str], avisos: list[str], ok: list[str]) -> str:
    linhas = ["### Conferência da configuração", ""]
    linhas += [f"- ✅ {item}" for item in ok]
    linhas += [f"- ⚠️ {item}" for item in avisos]
    linhas += [f"- ❌ {item}" for item in erros]
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    so_conferir = "--conferir" in argv
    token = os.environ.get("HF_TOKEN", "").strip()
    space = os.environ.get("HF_SPACE", "").strip() or SPACE_PADRAO
    link_space = f"https://huggingface.co/spaces/{space}"
    if not token:
        escrever_resumo(
            "## ❌ Falta o secret HF_TOKEN no GitHub\n\n"
            "No GitHub: Settings → Secrets and variables → Actions → New repository secret → "
            "nome `HF_TOKEN`, valor = token do Hugging Face com permissão de escrita no Space."
        )
        return 1

    from huggingface_hub import HfApi
    from huggingface_hub.errors import HfHubHTTPError

    api = HfApi(token=token)
    erros, avisos, ok = conferir(api, space, base_ativa=_base_ativa())
    escrever_resumo(relatorio(erros, avisos, ok))
    if erros:
        escrever_resumo("## ❌ Configuração incompleta: nada foi publicado. Corrija os itens com ❌.")
        return 1
    if so_conferir:
        escrever_resumo("## ✅ Configuração pronta para publicar")
        return 0

    print(f"Enviando para {space}:")
    for arquivo in arquivos_para_publicar():
        print(f"   {arquivo}")
    try:
        commit = enviar(api, space)
    except HfHubHTTPError as erro:
        escrever_resumo(f"## ❌ O Hugging Face recusou o envio\n\n{_explicar_erro_http(erro, space)}")
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
