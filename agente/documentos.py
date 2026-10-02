"""Pasta documentos/: o material de consulta do assistente (Parte 2).

Regras (spec da Parte 2, RF23 e RF24):
- só arquivos .md, direto na pasta (sem subpastas);
- cada arquivo tem um título "# ..." e pelo menos uma seção "## ..." com conteúdo;
- nada de dado pessoal (e-mail, CPF, telefone): o repositório é público.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agente.config import RAIZ_PROJETO

PASTA_PADRAO = RAIZ_PROJETO / "documentos"
TAMANHO_MAX = 1024 * 1024  # 1 MB por documento
PADRAO_NOME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")

PADRAO_TITULO = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
PADRAO_CERCA = re.compile(r"^\s*(```|~~~)")

# Dados pessoais detectáveis. O CPF só conta se os dígitos verificadores baterem,
# para não confundir com outros números de 11 dígitos.
PADRAO_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PADRAO_CPF = re.compile(r"(?<!\d)(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d)")
PADRAO_TELEFONE = re.compile(r"(?:\+55\s?)?\(?\b\d{2}\)?\s?9?\d{4}[-\s]\d{4}\b")


@dataclass(frozen=True)
class Titulo:
    nivel: int  # 1 = "#", 2 = "##", ...
    texto: str
    linha: int  # 1-based


def ler_titulos(texto: str) -> list[Titulo]:
    """Títulos Markdown do texto, ignorando o que está dentro de blocos de código."""
    titulos: list[Titulo] = []
    dentro_de_codigo = False
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if PADRAO_CERCA.match(linha):
            dentro_de_codigo = not dentro_de_codigo
            continue
        if dentro_de_codigo:
            continue
        m = PADRAO_TITULO.match(linha)
        if m:
            titulos.append(Titulo(len(m.group(1)), m.group(2).strip(), numero))
    return titulos


def _cpf_valido(digitos: str) -> bool:
    if len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * peso for d, peso in zip(digitos[:tamanho], range(tamanho + 1, 1, -1)))
        if int(digitos[tamanho]) != (soma * 10 % 11) % 10:
            return False
    return True


def dados_pessoais(texto: str) -> list[str]:
    """Descrições (sem o dado inteiro) do que parece dado pessoal no texto."""
    achados = []
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if PADRAO_EMAIL.search(linha):
            achados.append(f"linha {numero}: parece um e-mail")
        for m in PADRAO_CPF.finditer(linha):
            if _cpf_valido("".join(m.groups())):
                achados.append(f"linha {numero}: parece um CPF")
        if PADRAO_TELEFONE.search(linha):
            achados.append(f"linha {numero}: parece um telefone")
    return achados


def _conteudo_por_secao(texto: str, titulos: list[Titulo]) -> dict[int, str]:
    """Para cada título de nível 2, o texto até o próximo título de nível 1 ou 2."""
    linhas = texto.splitlines()
    secoes = [t for t in titulos if t.nivel <= 2]
    resultado = {}
    for i, titulo in enumerate(secoes):
        if titulo.nivel != 2:
            continue
        fim = secoes[i + 1].linha - 1 if i + 1 < len(secoes) else len(linhas)
        resultado[titulo.linha] = "\n".join(linhas[titulo.linha : fim]).strip()
    return resultado


def validar_documento(caminho: Path) -> list[str]:
    nome = caminho.name
    erros: list[str] = []
    if not PADRAO_NOME.match(nome):
        sugestao = re.sub(r"[^a-z0-9]+", "-", caminho.stem.lower()).strip("-") + ".md"
        erros.append(
            f'❌ documentos/{nome}: use só letras minúsculas, números e hífen no nome, por exemplo "{sugestao}".'
        )
    if caminho.stat().st_size > TAMANHO_MAX:
        erros.append(f"❌ documentos/{nome}: tem mais de 1 MB. Divida em arquivos menores.")
        return erros
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return erros + [f"❌ documentos/{nome}: não está em UTF-8. Salve o arquivo com codificação UTF-8."]

    titulos = ler_titulos(texto)
    if not titulos or titulos[0].nivel != 1:
        erros.append(
            f'❌ documentos/{nome}: precisa começar com um título de nível 1, por exemplo "# Apostila da Parte 1".'
        )
    secoes = _conteudo_por_secao(texto, titulos)
    if not secoes:
        erros.append(f'❌ documentos/{nome}: precisa de pelo menos uma seção "## ...". As seções viram a fonte citada.')
    elif not any(secoes.values()):
        erros.append(f'❌ documentos/{nome}: as seções estão vazias. Coloque o texto embaixo de cada "## ...".')
    for achado in dados_pessoais(texto):
        erros.append(f"❌ documentos/{nome}, {achado}. O repositório é público: tire dados pessoais antes do commit.")
    return erros


def validar_pasta(pasta: Path = PASTA_PADRAO) -> list[str]:
    """Erros da pasta documentos/ (lista vazia = tudo certo). Verificação T19."""
    if not pasta.is_dir():
        return ["❌ A pasta documentos/ não existe. Crie-a e coloque os arquivos .md do material de consulta."]
    erros: list[str] = []
    documentos = []
    for item in sorted(pasta.iterdir()):
        if item.name.startswith("."):
            continue  # .gitkeep e similares
        if item.is_dir():
            erros.append(f"❌ documentos/{item.name}/: não use subpastas; deixe os arquivos .md direto em documentos/.")
        elif item.suffix.lower() != ".md":
            erros.append(
                f"❌ documentos/{item.name}: só arquivos .md são aceitos. "
                "Converta PDF ou Word para Markdown, revise e apague o original da pasta."
            )
        else:
            documentos.append(item)
    if not documentos and not erros:
        erros.append("❌ A pasta documentos/ está vazia. Coloque pelo menos um arquivo .md.")
    for documento in documentos:
        erros += validar_documento(documento)
    return erros
