"""Testes do portão T16 e T17: o pacote do Space está coerente e o código limpo.

Pegam, ANTES de publicar, os erros que derrubariam o build no Hugging Face:
cabeçalho do README errado, versões diferentes, biblioteca faltando.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent

# Campos aceitos no cabeçalho (https://huggingface.co/docs/hub/spaces-config-reference)
CAMPOS_ACEITOS = {
    "title", "emoji", "colorFrom", "colorTo", "sdk", "python_version", "sdk_version",
    "suggested_hardware", "suggested_storage", "app_file", "app_build_command", "app_port",
    "base_path", "fullWidth", "header", "short_description", "models", "datasets", "tags",
    "thumbnail", "pinned", "hf_oauth", "hf_oauth_scopes", "hf_oauth_expiration_minutes",
    "hf_oauth_authorized_org", "disable_embedding", "startup_duration_timeout",
    "custom_headers", "license", "preload_from_hub",
}  # fmt: skip
CORES_ACEITAS = {"red", "yellow", "green", "blue", "indigo", "purple", "pink", "gray"}
PYTHON_ZEROGPU = ("3.10", "3.12")
SEM_VERSAO_FIXA = {"spaces"}  # o Hugging Face fornece a versão certa na ZeroGPU
NOME_NO_PIP = {"yaml": "pyyaml"}  # import -> nome do pacote


def ler_cabecalho() -> dict:
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    partes = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
    assert partes, "O README.md precisa começar com um bloco entre linhas '---'."
    return yaml.safe_load(partes.group(1))


def ler_requisitos() -> dict[str, str | None]:
    """{'gradio': '6.28.0', 'spaces': None, ...} (nomes em minúsculas)."""
    requisitos: dict[str, str | None] = {}
    for linha in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines():
        linha = linha.split("#")[0].strip()
        if not linha:
            continue
        nome, _, versao = linha.partition("==")
        nome = nome.strip().lower()
        assert nome not in requisitos, f"'{nome}' aparece duas vezes no requirements.txt"
        requisitos[nome] = versao.strip() or None
    return requisitos


# ------------------------------------------------------ T16: cabeçalho


def test_t16_cabecalho_tem_os_campos_essenciais():
    cabecalho = ler_cabecalho()
    for campo in ("title", "emoji", "sdk", "sdk_version", "python_version", "app_file"):
        assert cabecalho.get(campo), f"Campo '{campo}' ausente no cabeçalho do README.md"


def test_t16_sem_campos_desconhecidos():
    desconhecidos = set(ler_cabecalho()) - CAMPOS_ACEITOS
    assert not desconhecidos, f"Campos que o Hugging Face não reconhece: {desconhecidos}"


def test_t16_sdk_gradio_e_app_file_existe():
    cabecalho = ler_cabecalho()
    assert cabecalho["sdk"] == "gradio", "A ZeroGPU só funciona com sdk: gradio"
    assert (RAIZ / cabecalho["app_file"]).is_file(), f"app_file '{cabecalho['app_file']}' não existe"


def test_t16_versao_do_gradio_igual_no_readme_e_no_requirements():
    sdk_version = str(ler_cabecalho()["sdk_version"])
    fixada = ler_requisitos().get("gradio")
    assert fixada == sdk_version, (
        f"README.md diz sdk_version {sdk_version}, mas o requirements.txt fixa gradio=={fixada}. Deixe iguais."
    )


def test_t16_versao_do_gradio_instalada_e_a_mesma():
    import gradio

    assert gradio.__version__ == str(ler_cabecalho()["sdk_version"]), (
        "O Gradio instalado aqui é diferente do publicado; rode: pip install -r requirements-dev.txt"
    )


def test_t16_python_aceito_pela_zerogpu():
    versao = str(ler_cabecalho()["python_version"])
    assert versao.startswith(PYTHON_ZEROGPU), f"python_version {versao}: a ZeroGPU aceita {PYTHON_ZEROGPU}"


def test_t16_campos_visuais_validos():
    cabecalho = ler_cabecalho()
    assert cabecalho.get("colorFrom", "blue") in CORES_ACEITAS
    assert cabecalho.get("colorTo", "blue") in CORES_ACEITAS
    assert len(str(cabecalho.get("short_description", ""))) <= 60, "short_description: máximo de 60 caracteres"


# --------------------------------------------------- T16: requirements.txt


def test_t16_requisitos_com_versao_fixa():
    soltos = [nome for nome, versao in ler_requisitos().items() if versao is None and nome not in SEM_VERSAO_FIXA]
    assert not soltos, f"Fixe a versão (==) de: {soltos}"


def _imports_de_terceiros() -> set[str]:
    arquivos = [RAIZ / "app.py", *(RAIZ / "agente").glob("*.py")]
    nomes: set[str] = set()
    for arquivo in arquivos:
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                nomes |= {a.name.split(".")[0] for a in no.names}
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                nomes.add(no.module.split(".")[0])
    return {n for n in nomes if n not in sys.stdlib_module_names and n not in {"agente", "__future__"}}


def test_t16_toda_biblioteca_usada_esta_no_requirements():
    """Evita o erro clássico 'ModuleNotFoundError' no build do Space."""
    requisitos = ler_requisitos()
    faltando = [m for m in _imports_de_terceiros() if NOME_NO_PIP.get(m, m).lower() not in requisitos]
    assert not faltando, f"Adicione ao requirements.txt: {faltando}"


# ------------------------------------------------------------ T17: ruff


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff não instalado (pip install -r requirements-dev.txt)")
def test_t17_ruff_sem_erros():
    resultado = subprocess.run(["ruff", "check", str(RAIZ)], capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stdout
