"""Testes do pipeline (spec, seção 7): workflow do GitHub Actions e scripts/publicar.py.

Nada é enviado de verdade: o Hugging Face é simulado.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import publicar  # noqa: E402

WORKFLOW = RAIZ / ".github" / "workflows" / "deploy.yml"


# ------------------------------------------------------------- o workflow


@pytest.fixture(scope="module")
def workflow() -> dict:
    dados = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    dados["on"] = dados.pop(True, dados.get("on"))  # o YAML lê "on:" como True
    return dados


def _comandos(job: dict) -> str:
    return "\n".join(passo.get("run", "") for passo in job["steps"])


def test_roda_em_qualquer_branch_e_em_pull_requests(workflow):
    assert "push" in workflow["on"] and "pull_request" in workflow["on"]
    assert workflow["on"]["push"] is None or "branches" not in (workflow["on"]["push"] or {})


def test_job_testes_roda_todas_as_verificacoes(workflow):
    comandos = _comandos(workflow["jobs"]["testes"])
    for comando in (
        "pip install -r requirements-dev.txt",
        "python scripts/validar_config.py",  # T1–T7
        "python scripts/procurar_chaves.py",  # T8
        "ruff check .",  # T17
        "python -m pytest",  # T1–T17
    ):
        assert comando in comandos, f"falta no job 'testes': {comando}"


def test_verificacoes_rodam_mesmo_se_uma_anterior_falhar(workflow):
    passos = [p for p in workflow["jobs"]["testes"]["steps"] if "run" in p]
    depois_do_validador = passos[passos.index(next(p for p in passos if "validar_config" in p["run"])) + 1 :]
    assert all("!cancelled()" in str(p.get("if", "")) for p in depois_do_validador)


def test_publicar_so_depois_dos_testes_e_so_na_main(workflow):
    job = workflow["jobs"]["publicar"]
    assert job["needs"] == "testes"
    assert "refs/heads/main" in job["if"]
    assert "pull_request" in job["if"]
    assert job["concurrency"]["cancel-in-progress"] is False
    assert "python scripts/publicar.py" in _comandos(job)


def test_token_vem_do_secret_e_nao_do_codigo(workflow):
    passo = next(p for p in workflow["jobs"]["publicar"]["steps"] if "publicar.py" in p.get("run", ""))
    assert passo["env"]["HF_TOKEN"] == "${{ secrets.HF_TOKEN }}"
    assert workflow["permissions"] == {"contents": "read"}


def test_python_do_ci_igual_ao_do_space(workflow):
    cabecalho = yaml.safe_load(re.match(r"^---\n(.*?)\n---\n", (RAIZ / "README.md").read_text("utf-8"), re.S)[1])
    for job in workflow["jobs"].values():
        versoes = [p["with"]["python-version"] for p in job["steps"] if "setup-python" in p.get("uses", "")]
        assert versoes == [str(cabecalho["python_version"])]


def test_versao_do_huggingface_hub_igual_no_ci_e_nos_testes(workflow):
    no_ci = re.search(r"huggingface_hub==([\d.]+)", _comandos(workflow["jobs"]["publicar"]))[1]
    nos_testes = re.search(r"huggingface_hub==([\d.]+)", (RAIZ / "requirements-dev.txt").read_text("utf-8"))[1]
    assert no_ci == nos_testes


# ------------------------------------------------ o que vai para o Space


def test_envia_so_os_arquivos_do_app():
    arquivos = publicar.arquivos_para_publicar()
    for essencial in ("README.md", "app.py", "config.yaml", "requirements.txt", "agente/roteador.py"):
        assert essencial in arquivos
    assert any(a.startswith("assets/") for a in arquivos)
    for proibido in ("tests/", "scripts/", ".github/", "SPEC-", "IDEIA-", "requirements-dev", "__pycache__", ".env"):
        assert not any(proibido in a for a in arquivos), f"não deveria publicar {proibido}"


def test_envia_com_os_parametros_certos(monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "abc1234def")
    chamadas = {}

    class ApiFalsa:
        def upload_folder(self, **kwargs):
            chamadas.update(kwargs)
            return SimpleNamespace(oid="novo", commit_url="https://hf/commit/novo")

    commit = publicar.enviar(ApiFalsa(), "thiagoazro/agente-personalizado")
    assert commit.oid == "novo"
    assert chamadas["repo_id"] == "thiagoazro/agente-personalizado"
    assert chamadas["repo_type"] == "space"
    assert chamadas["allow_patterns"] == publicar.ARQUIVOS_DO_APP
    assert chamadas["delete_patterns"] == ["*"]  # remove do Space o que foi apagado no GitHub
    assert "abc1234" in chamadas["commit_message"]


# ------------------------------------------------- acompanhamento do build


class ApiComEstados:
    """Devolve uma sequência de estados do Space, um por consulta."""

    def __init__(self, *estados: str | tuple[str, str]):
        self.estados = list(estados)

    def get_space_runtime(self, _space):
        atual = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
        estagio, sha = atual if isinstance(atual, tuple) else (atual, None)
        return SimpleNamespace(stage=estagio, raw={"sha": sha} if sha else {})


def aguardar(api, **kwargs):
    relogio = {"t": 0.0}

    def dormir(segundos):
        relogio["t"] += segundos

    return publicar.aguardar_build(api, "u/s", dormir=dormir, agora=lambda: relogio["t"], **kwargs)


def test_build_ok():
    assert aguardar(ApiComEstados("BUILDING", "APP_STARTING", "RUNNING")) == (True, "no ar (RUNNING)")


@pytest.mark.parametrize("erro", ["BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"])
def test_build_com_erro_falha(erro):
    sucesso, detalhe = aguardar(ApiComEstados("BUILDING", erro))
    assert sucesso is False and erro in detalhe


def test_nao_confunde_versao_antiga_rodando_com_sucesso():
    api = ApiComEstados(("RUNNING", "antigo"), ("BUILDING", None), ("RUNNING", "novo"))
    assert aguardar(api, sha_esperado="novo") == (True, "no ar (RUNNING)")
    assert api.estados == [("RUNNING", "novo")]  # consultou até ver a versão nova


def test_space_dormindo_conta_como_publicado():
    sucesso, detalhe = aguardar(ApiComEstados("SLEEPING"))
    assert sucesso and "acorda na próxima visita" in detalhe


def test_build_demorado_nao_fica_vermelho():
    sucesso, detalhe = aguardar(ApiComEstados("BUILDING"), limite_segundos=60)
    assert sucesso and "ainda não terminou" in detalhe


def test_estado_como_enum_do_huggingface_hub():
    from huggingface_hub import SpaceStage

    api = SimpleNamespace(get_space_runtime=lambda _s: SimpleNamespace(stage=SpaceStage.RUNNING, raw={}))
    assert aguardar(api) == (True, "no ar (RUNNING)")


# --------------------------------------------------------------- main()


@pytest.fixture
def resumo(tmp_path, monkeypatch) -> Path:
    arquivo = tmp_path / "resumo.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(arquivo))
    return arquivo


def test_sem_hf_token_explica_o_que_fazer(monkeypatch, resumo):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert publicar.main() == 1
    assert "falta o secret HF_TOKEN" in resumo.read_text("utf-8")


def _erro_http(classe, status):
    resposta = httpx.Response(status, request=httpx.Request("POST", "https://huggingface.co/api"))
    return classe("erro", response=resposta)


@pytest.mark.parametrize(
    "status,esperado",
    [(401, "HF_TOKEN está inválido"), (403, "sem permissão de escrita"), (500, "Tente rodar o job de novo")],
)
def test_envio_recusado_explica_o_motivo(status, esperado, monkeypatch, resumo):
    from huggingface_hub.errors import HfHubHTTPError

    class ApiFalsa:
        def __init__(self, token):
            pass

        def upload_folder(self, **_):
            raise _erro_http(HfHubHTTPError, status)

    monkeypatch.setenv("HF_TOKEN", "token-de-teste")
    monkeypatch.setattr("huggingface_hub.HfApi", ApiFalsa)
    assert publicar.main() == 1
    texto = resumo.read_text("utf-8")
    assert f"({status})" in texto and esperado in texto
    assert "token-de-teste" not in texto


def test_space_inexistente(monkeypatch, resumo):
    from huggingface_hub.errors import RepositoryNotFoundError

    class ApiFalsa:
        def __init__(self, token):
            pass

        def upload_folder(self, **_):
            raise _erro_http(RepositoryNotFoundError, 404)

    monkeypatch.setenv("HF_TOKEN", "t")
    monkeypatch.setenv("HF_SPACE", "fulano/nao-existe")
    monkeypatch.setattr("huggingface_hub.HfApi", ApiFalsa)
    assert publicar.main() == 1
    assert "`fulano/nao-existe` não encontrado" in resumo.read_text("utf-8")


def test_publicacao_completa_com_sucesso(monkeypatch, resumo):
    class ApiFalsa:
        def __init__(self, token):
            pass

        def upload_folder(self, **_):
            return SimpleNamespace(oid="n", commit_url="https://hf/c/n")

        def get_space_runtime(self, _):
            return SimpleNamespace(stage="RUNNING", raw={"sha": "n"})

    monkeypatch.setenv("HF_TOKEN", "t")
    monkeypatch.delenv("HF_SPACE", raising=False)
    monkeypatch.setattr("huggingface_hub.HfApi", ApiFalsa)
    monkeypatch.setattr(publicar.time, "sleep", lambda _s: None)
    assert publicar.main() == 0
    texto = resumo.read_text("utf-8")
    assert "✅ Publicado" in texto
    assert "https://huggingface.co/spaces/thiagoazro/agente-personalizado" in texto
