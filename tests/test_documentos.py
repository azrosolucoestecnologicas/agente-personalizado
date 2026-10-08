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


# ================================================================= T20
# Divisão em trechos (spec da Parte 2, RF25 e RF26).

from agente.documentos import (  # noqa: E402
    SEPARADOR_SECAO,
    TAMANHO_MINIMO_SECAO,
    Trecho,
    dividir_documento,
    dividir_pasta,
)


def _escrever(pasta: Path, texto: str, nome: str = "doc.md") -> Path:
    caminho = pasta / nome
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _corpo(trecho: Trecho) -> str:
    return trecho.conteudo.split("\n\n", 1)[1]


PARAGRAFO = "Frase de exemplo sobre deploy e segredos no GitHub Actions. " * 6  # ~360 caracteres


@pytest.fixture(scope="module")
def trechos_reais() -> list[Trecho]:
    return dividir_pasta(tamanho_trecho=1500, sobreposicao=200)


# ------------------------------------------------------ com as apostilas


def test_t20_titulo_repetido_no_inicio_de_cada_trecho(trechos_reais):
    for t in trechos_reais:
        assert t.conteudo.startswith(t.secao + "\n\n"), t.secao


def test_t20_nenhum_trecho_passa_do_tamanho(trechos_reais):
    assert max(len(t.conteudo) for t in trechos_reais) <= 1500


@pytest.mark.parametrize("tamanho,sobreposicao", [(300, 50), (800, 120), (1500, 200), (3000, 500)])
def test_t20_limite_vale_para_qualquer_configuracao(tamanho, sobreposicao):
    trechos = dividir_pasta(tamanho_trecho=tamanho, sobreposicao=sobreposicao)
    assert max(len(t.conteudo) for t in trechos) <= tamanho


def test_t20_metadados_preenchidos_e_ordem_sequencial(trechos_reais):
    for fonte in {t.fonte for t in trechos_reais}:
        do_documento = [t for t in trechos_reais if t.fonte == fonte]
        assert [t.ordem for t in do_documento] == list(range(len(do_documento)))
        assert all(t.secao and t.conteudo.strip() for t in do_documento)


def test_t20_toda_secao_e_subsecao_aparece_em_algum_trecho(trechos_reais):
    for documento in PASTA_PADRAO.glob("*.md"):
        secoes = " | ".join(t.secao for t in trechos_reais if t.fonte == documento.name)
        conteudos = "\n".join(t.conteudo for t in trechos_reais if t.fonte == documento.name)
        for titulo in ler_titulos(documento.read_text(encoding="utf-8")):
            if titulo.nivel == 2:
                assert titulo.texto in secoes, titulo.texto
            elif titulo.nivel == 3:
                assert titulo.texto in secoes or f"**{titulo.texto}" in conteudos, titulo.texto


def test_t20_nenhum_texto_se_perde(trechos_reais):
    """Cada linha de texto do documento está em algum trecho."""
    for documento in PASTA_PADRAO.glob("*.md"):
        conteudos = "\n".join(t.conteudo for t in trechos_reais if t.fonte == documento.name)
        for linha in documento.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and not linha.startswith("```") and len(linha) > 3:
                assert linha in conteudos, linha[:80]


def test_t20_nao_sobra_trecho_curto_demais(trechos_reais):
    curtos = [t.secao for t in trechos_reais if len(_corpo(t)) < TAMANHO_MINIMO_SECAO]
    assert curtos == []


def test_t20_apostilas_viram_algumas_centenas_de_trechos(trechos_reais):
    assert 60 <= len(trechos_reais) <= 300  # "poucas centenas", como diz a apostila


def test_t20_titulos_dentro_de_codigo_nao_viram_secao(trechos_reais):
    assert not any("Ideia do projeto" in t.secao for t in trechos_reais)
    assert any("Apêndice A" in t.secao and "# Ideia do projeto" in t.conteudo for t in trechos_reais)


# --------------------------------------------------------- casos de regra


def test_t20_secao_longa_e_subdividida_com_sobreposicao(tmp_path):
    texto = "# Doc\n\n## 01 Longa\n\n" + "\n\n".join(f"{i} " + PARAGRAFO for i in range(8))
    trechos = dividir_documento(_escrever(tmp_path, texto), tamanho_trecho=1000, sobreposicao=150)
    assert len(trechos) > 2
    assert all(len(t.conteudo) <= 1000 and t.secao == "01 Longa" for t in trechos)
    for anterior, seguinte in zip(trechos, trechos[1:]):
        inicio = _corpo(seguinte).split("\n\n")[0]
        assert inicio in _corpo(anterior)  # o começo do seguinte repete o fim do anterior
        assert len(inicio) <= 150


def test_t20_sem_sobreposicao_quando_zero(tmp_path):
    texto = "# Doc\n\n## 01 Longa\n\n" + "\n\n".join(f"{i} " + PARAGRAFO for i in range(8))
    trechos = dividir_documento(_escrever(tmp_path, texto), tamanho_trecho=1000, sobreposicao=0)
    juntos = sum(len(_corpo(t)) for t in trechos)
    original = len(texto.split("## 01 Longa\n\n")[1])
    assert juntos <= original + 2 * len(trechos)  # nada repetido


def test_t20_secao_curta_junta_com_a_seguinte(tmp_path):
    texto = "# Doc\n\n## 01 Mãe\n\n### Curta\n\nPouco texto.\n\n### Longa\n\n" + PARAGRAFO
    trechos = dividir_documento(_escrever(tmp_path, texto))
    assert len(trechos) == 1
    assert trechos[0].secao == "01 Mãe" + SEPARADOR_SECAO + "Curta / Longa"
    assert "Pouco texto." in trechos[0].conteudo and "**Longa**" in trechos[0].conteudo


def test_t20_ultima_secao_curta_junta_com_a_anterior(tmp_path):
    texto = "# Doc\n\n## 01 Mãe\n\n" + PARAGRAFO + "\n\n### Fim curto\n\nSó isso."
    trechos = dividir_documento(_escrever(tmp_path, texto))
    assert len(trechos) == 1
    assert "**Fim curto**" in trechos[0].conteudo


def test_t20_nao_junta_secoes_de_maes_diferentes(tmp_path):
    texto = "# Doc\n\n## 01 Uma\n\nCurto.\n\n## 02 Outra\n\n" + PARAGRAFO
    secoes = [t.secao for t in dividir_documento(_escrever(tmp_path, texto))]
    assert secoes == ["01 Uma", "02 Outra"]


def test_t20_texto_de_abertura_usa_o_titulo_do_documento(tmp_path):
    texto = "# Minha Apostila\n\n" + PARAGRAFO + "\n\n## 01 Seção\n\n" + PARAGRAFO
    trechos = dividir_documento(_escrever(tmp_path, texto))
    assert trechos[0].secao == "Minha Apostila"


def test_t20_tabela_grande_repete_o_cabecalho(tmp_path):
    linhas = "\n".join(f"|Linha {i}|{'texto de exemplo ' * 5}|" for i in range(40))
    texto = f"# Doc\n\n## 01 Tabela\n\n|**A**|**B**|\n|---|---|\n{linhas}\n"
    trechos = dividir_documento(_escrever(tmp_path, texto), tamanho_trecho=800, sobreposicao=100)
    assert len(trechos) > 2
    for t in trechos:
        assert len(t.conteudo) <= 800
        assert "|**A**|**B**|\n|---|---|" in t.conteudo  # todo pedaço tem o cabeçalho da tabela


def test_t20_bloco_de_codigo_grande_fica_com_as_cercas(tmp_path):
    codigo = "\n".join(f"linha_{i} = {i} * 2  # comentário" for i in range(80))
    texto = f"# Doc\n\n## 01 Código\n\n```\n{codigo}\n```\n"
    trechos = dividir_documento(_escrever(tmp_path, texto), tamanho_trecho=800, sobreposicao=100)
    assert len(trechos) > 2
    for t in trechos:
        assert len(t.conteudo) <= 800
        assert _corpo(t).count("```") % 2 == 0  # nenhum pedaço com bloco de código aberto


def test_t20_paragrafo_gigante_e_quebrado_por_frases(tmp_path):
    texto = "# Doc\n\n## 01 Parágrafo\n\n" + "Uma frase completa sobre o assunto. " * 120
    trechos = dividir_documento(_escrever(tmp_path, texto), tamanho_trecho=600, sobreposicao=80)
    assert all(len(t.conteudo) <= 600 for t in trechos)
    assert all(_corpo(t).rstrip().endswith(".") for t in trechos)  # corta entre frases
