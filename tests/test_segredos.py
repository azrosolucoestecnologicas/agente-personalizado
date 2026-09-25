"""Testes do portão T8: varredura de chaves de API.

As chaves falsas são montadas em partes (ex.: "sk-" + "ant-") para que
este próprio arquivo não seja apontado pela varredura.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agente.segredos import procurar_em_texto, tem_chave

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "procurar_chaves.py"

CHAVES_FALSAS = {
    "chave do OpenRouter": "sk-" + "or-v1-" + "0123456789abcdef" * 4,
    "chave da Anthropic": "sk-" + "ant-api03-" + "Ab1_" * 10,
    "chave da OpenAI": "sk-" + "proj-" + "Xy9-" * 10,
    "chave no formato sk-": "sk-" + "A1b2C3d4" * 5,
    "token do Hugging Face": "hf" + "_" + "AbCdEfGhIj" * 4,
}


def rodar(pasta: Path, **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(pasta)], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", **env}
    )


# -------------------------------------------------------- detecção no texto


@pytest.mark.parametrize("tipo,chave", CHAVES_FALSAS.items())
def test_t8_detecta_cada_tipo_de_chave(tipo, chave):
    achados = procurar_em_texto(f'cliente = Cliente(api_key="{chave}")')
    assert [a.tipo for a in achados] == [tipo]


@pytest.mark.parametrize(
    "linha",
    [
        'OPENAI_API_KEY = "' + "abc123XYZ" * 3 + '"',
        "ANTHROPIC_API_KEY=" + "q" * 20,
        "OPENROUTER_API_KEY: " + "z9" * 10,
        '"HF_TOKEN": "' + "t" * 20 + '"',
    ],
)
def test_t8_detecta_chave_escrita_direto_no_codigo(linha):
    assert [a.tipo for a in procurar_em_texto(linha)] == ["chave escrita direto no código"]


@pytest.mark.parametrize(
    "linha",
    [
        'chave = os.environ["OPENAI_API_KEY"]',
        'chave = os.environ.get("ANTHROPIC_API_KEY", "")',
        "HF_TOKEN: ${{ secrets.HF_TOKEN }}",
        "| `OPENROUTER_API_KEY` | Sua chave do OpenRouter (começa com `sk-or-`) |",
        "task-runner e disk-usage não são chaves",
        "sk-curto",
        "mask_hf_logo_skin",
    ],
)
def test_t8_nao_acusa_textos_normais(linha):
    assert not tem_chave(linha)


def test_t8_chave_nunca_aparece_inteira():
    chave = CHAVES_FALSAS["chave da Anthropic"]
    achado = procurar_em_texto(chave)[0]
    assert chave not in achado.trecho
    assert achado.trecho.startswith("sk-ant")
    assert "oculto" in achado.trecho


def test_t8_uma_chave_conta_uma_vez():
    assert len(procurar_em_texto(CHAVES_FALSAS["chave do OpenRouter"])) == 1


# ------------------------------------------------------ script de varredura


def test_t8_repositorio_do_projeto_esta_limpo():
    resultado = rodar(RAIZ)
    assert resultado.returncode == 0, resultado.stdout
    assert "✅" in resultado.stdout


def test_t8_pasta_limpa(tmp_path):
    (tmp_path / "app.py").write_text('import os\nchave = os.environ["OPENAI_API_KEY"]\n', encoding="utf-8")
    assert rodar(tmp_path).returncode == 0


def test_t8_bloqueia_chave_e_mostra_arquivo_e_linha(tmp_path):
    chave = CHAVES_FALSAS["chave da OpenAI"]
    (tmp_path / "app.py").write_text(f'print("oi")\nchave = "{chave}"\n', encoding="utf-8")
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "app.py:2: chave da OpenAI" in resultado.stdout
    assert "REVOGUE" in resultado.stdout
    assert chave not in resultado.stdout + resultado.stderr


def test_t8_varre_subpastas_e_qualquer_extensao(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "anotacoes.md").write_text(CHAVES_FALSAS["token do Hugging Face"], encoding="utf-8")
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "docs/anotacoes.md:1" in resultado.stdout


@pytest.mark.parametrize("nome", [".env", ".env.local", "producao.env"])
def test_t8_bloqueia_arquivo_env(nome, tmp_path):
    (tmp_path / nome).write_text("NADA=1\n", encoding="utf-8")
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "arquivo .env não pode ir para o repositório" in resultado.stdout


def test_t8_pula_arquivos_binarios(tmp_path):
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\0\0" + CHAVES_FALSAS["chave da Anthropic"].encode())
    assert rodar(tmp_path).returncode == 0


def test_t8_escreve_resumo_no_actions(tmp_path):
    (tmp_path / "x.py").write_text(CHAVES_FALSAS["chave do OpenRouter"], encoding="utf-8")
    resumo = tmp_path.parent / f"{tmp_path.name}-resumo.md"
    rodar(tmp_path, GITHUB_STEP_SUMMARY=str(resumo))
    texto = resumo.read_text(encoding="utf-8")
    assert "x.py:1" in texto
    assert CHAVES_FALSAS["chave do OpenRouter"] not in texto


def test_t8_em_repositorio_git_respeita_gitignore(tmp_path):
    """Um .env ignorado pelo .gitignore não vai para o GitHub, então não bloqueia."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=" + "k" * 30 + "\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('oi')\n", encoding="utf-8")
    assert rodar(tmp_path).returncode == 0

    # Mas se alguém forçar o .env para dentro do Git, bloqueia.
    subprocess.run(["git", "add", "-f", ".env"], cwd=tmp_path, check=True)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert ".env" in resultado.stdout
