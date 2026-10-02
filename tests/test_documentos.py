"""Testes do portão T19: a pasta documentos/ (spec da Parte 2, RF23 e RF24)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agente.documentos import PASTA_PADRAO, dados_pessoais, ler_titulos, validar_pasta

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "validar_documentos.py"

DOC_OK = "# Apostila\n\nIntrodução.\n\n## 01 Primeira seção\n\nTexto da seção.\n"


@pytest.fixture
def pasta(tmp_path: Path) -> Path:
    p = tmp_path / "documentos"
    p.mkdir()
    (p / "apostila.md").write_text(DOC_OK, encoding="utf-8")
    return p


def erros(pasta: Path) -> str:
    return "\n".join(validar_pasta(pasta))


# --------------------------------------------------------- pasta do projeto


def test_t19_documentos_do_projeto_validos():
    assert validar_pasta() == []


def test_t19_apostilas_presentes_com_secoes():
    nomes = {p.name for p in PASTA_PADRAO.glob("*.md")}
    assert {"parte1-cicd-deploy.md", "parte2-rag.md"} <= nomes
    for nome, secoes in (("parte1-cicd-deploy.md", 15), ("parte2-rag.md", 21)):
        titulos = ler_titulos((PASTA_PADRAO / nome).read_text(encoding="utf-8"))
        assert sum(t.nivel == 2 for t in titulos) == secoes
        assert sum(t.nivel == 1 for t in titulos) == 1


def test_t19_conversao_sem_restos_do_pdf():
    """Nada de diagrama embaralhado, cabeçalho de página ou negrito picotado."""
    for documento in PASTA_PADRAO.glob("*.md"):
        texto = documento.read_text(encoding="utf-8")
        assert "picture text" not in texto, documento.name
        assert "Material de consulta. A aula é prática" not in texto, documento.name
        assert "<br>" not in texto, documento.name
        assert "** **" not in texto, documento.name


def test_t19_script_ok():
    resultado = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stdout
    assert "parte2-rag.md: 21 seções" in resultado.stdout


# ---------------------------------------------------------------- regras


def test_t19_pasta_ausente(tmp_path):
    assert "não existe" in erros(tmp_path / "documentos")


def test_t19_pasta_vazia(tmp_path):
    (tmp_path / "documentos").mkdir()
    assert "está vazia" in erros(tmp_path / "documentos")


def test_t19_pasta_valida(pasta):
    assert validar_pasta(pasta) == []


@pytest.mark.parametrize("nome", ["apostila.pdf", "contrato.docx", "notas.txt"])
def test_t19_so_markdown(nome, pasta):
    (pasta / nome).write_bytes(b"x")
    assert f"documentos/{nome}: só arquivos .md" in erros(pasta)


def test_t19_arquivos_ocultos_sao_ignorados(pasta):
    (pasta / ".gitkeep").write_text("", encoding="utf-8")
    assert validar_pasta(pasta) == []


def test_t19_subpasta_nao_aceita(pasta):
    (pasta / "extras").mkdir()
    assert "não use subpastas" in erros(pasta)


def test_t19_nome_do_arquivo(pasta):
    (pasta / "Apostila Parte 3.md").write_text(DOC_OK, encoding="utf-8")
    assert 'por exemplo "apostila-parte-3.md"' in erros(pasta)


def test_t19_precisa_de_titulo_nivel_1(pasta):
    (pasta / "sem-titulo.md").write_text("## Seção\n\nTexto.\n", encoding="utf-8")
    assert "documentos/sem-titulo.md: precisa começar com um título de nível 1" in erros(pasta)


def test_t19_precisa_de_secao(pasta):
    (pasta / "sem-secao.md").write_text("# Título\n\nSó um parágrafo.\n", encoding="utf-8")
    assert "precisa de pelo menos uma seção" in erros(pasta)


def test_t19_secao_vazia(pasta):
    (pasta / "vazio.md").write_text("# Título\n\n## Seção\n\n", encoding="utf-8")
    assert "as seções estão vazias" in erros(pasta)


def test_t19_arquivo_grande_demais(pasta):
    (pasta / "grande.md").write_text("# T\n\n## S\n\n" + "a" * (1024 * 1024 + 1), encoding="utf-8")
    assert "mais de 1 MB" in erros(pasta)


def test_t19_arquivo_fora_de_utf8(pasta):
    (pasta / "latin.md").write_bytes("# Título\n\n## Seção\n\nAção\n".encode("latin-1"))
    assert "não está em UTF-8" in erros(pasta)


# ----------------------------------------------------- títulos em código


def test_titulos_dentro_de_codigo_sao_ignorados():
    texto = "# Doc\n\n## Seção real\n\n```\n# Não é título\n## Também não\n```\n\n### Sub\n"
    assert [(t.nivel, t.texto) for t in ler_titulos(texto)] == [(1, "Doc"), (2, "Seção real"), (3, "Sub")]


# -------------------------------------------------------- dados pessoais


@pytest.mark.parametrize(
    "linha,tipo",
    [
        ("Contato: fulano.silva@empresa.com.br", "e-mail"),
        ("CPF 529.982.247-25 do aluno", "CPF"),
        ("CPF 52998224725", "CPF"),
        ("Ligue (11) 91234-5678", "telefone"),
        ("WhatsApp +55 21 98765 4321", "telefone"),
    ],
)
def test_t19_detecta_dado_pessoal(linha, tipo, pasta):
    (pasta / "dados.md").write_text(f"# T\n\n## S\n\n{linha}\n", encoding="utf-8")
    assert f"linha 5: parece um {tipo}" in erros(pasta)
    assert "O repositório é público" in erros(pasta)


@pytest.mark.parametrize(
    "linha",
    [
        "O índice é uma matriz 1.000 × 384.",
        "Aula de 01/10, Parte 3 (08/10).",
        "Número qualquer 12345678901 que não é CPF.",
        "hit rate@3 = 3/4 = 0,75",
        "cron '0 11 * * *' às 11h UTC",
    ],
)
def test_nao_acusa_textos_normais(linha):
    assert dados_pessoais(linha) == []


def test_mensagem_nao_mostra_o_dado(pasta):
    (pasta / "dados.md").write_text("# T\n\n## S\n\nCPF 529.982.247-25\n", encoding="utf-8")
    assert "529.982.247-25" not in erros(pasta)
