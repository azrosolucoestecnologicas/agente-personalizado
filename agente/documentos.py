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


# ----------------------------------------------------------- divisão em trechos
#
# Estratégia "por estrutura" (seção 09 da apostila da Parte 2): cada seção (##)
# e subseção (###) vira uma unidade; o caminho de títulos vira metadado E é
# repetido no início do texto do trecho, antes do embedding.

SEPARADOR_SECAO = " > "
TAMANHO_MINIMO_SECAO = 200  # seções menores que isso são juntadas à seguinte (RF25)


@dataclass(frozen=True)
class Trecho:
    fonte: str  # nome do arquivo, ex.: parte2-rag.md
    secao: str  # caminho de títulos, ex.: "09 Chunking: dividir para achar > Estratégias de chunking"
    ordem: int  # posição do trecho dentro do documento (0, 1, 2, ...)
    conteudo: str  # começa com a seção; é o texto do embedding e da busca por palavras


@dataclass
class _Unidade:
    secao_mae: str  # título ## (ou o título # para o texto de abertura)
    subsecoes: list[str]  # títulos ### que entraram nesta unidade
    corpo: str

    @property
    def secao(self) -> str:
        if not self.subsecoes:
            return self.secao_mae
        return self.secao_mae + SEPARADOR_SECAO + " / ".join(self.subsecoes)


def _unidades(texto: str) -> list[list[_Unidade]]:
    """Agrupa o texto em unidades por seção. Cada grupo = uma seção ## (ou a abertura)."""
    grupos: list[list[_Unidade]] = []
    titulo_documento = ""
    atual: _Unidade | None = None
    linhas_atual: list[str] = []
    dentro_de_codigo = False

    def fechar():
        if atual is not None:
            atual.corpo = "\n".join(linhas_atual).strip()
            if atual.corpo:
                grupos[-1].append(atual)

    for linha in texto.splitlines():
        if PADRAO_CERCA.match(linha):
            dentro_de_codigo = not dentro_de_codigo
        m = None if dentro_de_codigo or PADRAO_CERCA.match(linha) else PADRAO_TITULO.match(linha)
        nivel = len(m.group(1)) if m else 0
        if nivel == 1:
            fechar()
            titulo_documento = m.group(2).strip()
            grupos.append([])
            atual, linhas_atual = _Unidade(titulo_documento, [], ""), []
        elif nivel == 2:
            fechar()
            grupos.append([])
            atual, linhas_atual = _Unidade(m.group(2).strip(), [], ""), []
        elif nivel == 3:
            fechar()
            mae = atual.secao_mae if atual else titulo_documento
            if not grupos:
                grupos.append([])
            atual, linhas_atual = _Unidade(mae, [m.group(2).strip()], ""), []
        else:
            if atual is None:  # texto antes de qualquer título
                grupos.append([])
                atual = _Unidade(titulo_documento or "Documento", [], "")
            linhas_atual.append(linha)
    fechar()
    return [g for g in grupos if g]


def _juntar(a: _Unidade, b: _Unidade) -> _Unidade:
    """Une duas unidades da mesma seção-mãe; o subtítulo da segunda fica no texto, em negrito."""
    corpo_b = (f"**{' / '.join(b.subsecoes)}**\n\n" if b.subsecoes else "") + b.corpo
    return _Unidade(a.secao_mae, a.subsecoes + b.subsecoes, a.corpo + "\n\n" + corpo_b)


def _juntar_pequenas(grupo: list[_Unidade]) -> list[_Unidade]:
    """RF25: seção curta (< 200 caracteres) é juntada à seguinte da mesma seção-mãe."""
    resultado: list[_Unidade] = []
    pendente: _Unidade | None = None
    for i, unidade in enumerate(grupo):
        if pendente is not None:
            unidade, pendente = _juntar(pendente, unidade), None
        if len(unidade.corpo) < TAMANHO_MINIMO_SECAO and i < len(grupo) - 1:
            pendente = unidade
            continue
        resultado.append(unidade)
    if pendente is not None:
        resultado.append(pendente)
    # A última, se for curta, vai para a anterior (não há "seguinte" na mesma seção-mãe).
    if len(resultado) >= 2 and len(resultado[-1].corpo) < TAMANHO_MINIMO_SECAO:
        ultima = resultado.pop()
        resultado[-1] = _juntar(resultado[-1], ultima)
    return resultado


def _blocos(corpo: str) -> list[str]:
    """Parágrafos, mas tabela e bloco de código ficam inteiros."""
    blocos: list[str] = []
    atual: list[str] = []
    dentro_de_codigo = False
    for linha in corpo.splitlines():
        if PADRAO_CERCA.match(linha):
            if not dentro_de_codigo and atual:
                blocos.append("\n".join(atual))
                atual = []
            dentro_de_codigo = not dentro_de_codigo
            atual.append(linha)
            if not dentro_de_codigo:
                blocos.append("\n".join(atual))
                atual = []
            continue
        if dentro_de_codigo:
            atual.append(linha)
        elif not linha.strip():
            if atual:
                blocos.append("\n".join(atual))
                atual = []
        else:
            eh_tabela, era_tabela = linha.startswith("|"), bool(atual) and atual[-1].startswith("|")
            if atual and eh_tabela != era_tabela:  # tabela começa ou termina sem linha em branco
                blocos.append("\n".join(atual))
                atual = []
            atual.append(linha)
    if atual:
        blocos.append("\n".join(atual))
    return [b.strip("\n") for b in blocos if b.strip()]


def _agrupar(partes: list[str], maximo: int, junta: str) -> list[str]:
    grupos: list[str] = []
    atual = ""
    for parte in partes:
        while len(parte) > maximo:  # último recurso: corta no limite
            corte = parte.rfind(" ", 0, maximo)
            corte = corte if corte > maximo // 2 else maximo
            if atual:
                grupos.append(atual)
                atual = ""
            grupos.append(parte[:corte].rstrip())
            parte = parte[corte:].lstrip()
        candidato = atual + junta + parte if atual else parte
        if len(candidato) <= maximo:
            atual = candidato
        else:
            grupos.append(atual)
            atual = parte
    if atual:
        grupos.append(atual)
    return grupos


def _quebrar(bloco: str, maximo: int) -> list[str]:
    """Quebra um bloco grande demais respeitando o formato dele."""
    if len(bloco) <= maximo:
        return [bloco]
    linhas = bloco.splitlines()
    if PADRAO_CERCA.match(linhas[0]):  # código: por linhas, cada pedaço com as cercas
        cerca, miolo = linhas[0], linhas[1:-1] if PADRAO_CERCA.match(linhas[-1]) else linhas[1:]
        pedacos = _agrupar(miolo, maximo - len(cerca) - 5, "\n")
        return [f"{cerca}\n{p}\n```" for p in pedacos]
    if bloco.startswith("|") and len(linhas) > 2:  # tabela: por linhas, repetindo o cabeçalho
        cabecalho = "\n".join(linhas[:2])
        pedacos = _agrupar(linhas[2:], maximo - len(cabecalho) - 1, "\n")
        return [f"{cabecalho}\n{p}" for p in pedacos]
    frases = re.split(r"(?<=[.!?;:])\s+", bloco)  # texto: por frases
    return _agrupar(frases, maximo, " ")


def _rabo(texto: str, tamanho: int) -> str:
    """O fim do trecho anterior, começando numa palavra inteira (a sobreposição)."""
    if tamanho <= 0 or len(texto) <= tamanho:
        return "" if tamanho <= 0 else texto
    rabo = texto[-tamanho:]
    # Começa no início de uma linha, se houver (não corta linha de tabela ou de lista);
    # senão, no início de uma palavra.
    quebra = re.search(r"\n", rabo) or re.search(r"\s", rabo)
    rabo = rabo[quebra.end() :] if quebra else rabo
    if rabo.count("```") % 2:  # não começar no meio de um bloco de código
        return ""
    return rabo.strip()


def _dividir_corpo(corpo: str, limite: int, sobreposicao: int) -> list[str]:
    """Corpo da seção em pedaços de até `limite` caracteres, com sobreposição."""
    if len(corpo) <= limite:
        return [corpo]
    sobreposicao = min(sobreposicao, limite // 3)  # garante que cada pedaço avance
    maximo_peca = limite - sobreposicao - 2
    pecas = [p for bloco in _blocos(corpo) for p in _quebrar(bloco, maximo_peca)]
    pedacos: list[str] = []
    atual = ""
    for peca in pecas:
        candidato = atual + "\n\n" + peca if atual else peca
        if len(candidato) <= limite:
            atual = candidato
            continue
        pedacos.append(atual)
        rabo = _rabo(atual, sobreposicao)
        atual = rabo + "\n\n" + peca if rabo else peca
    if atual:
        pedacos.append(atual)
    return pedacos


def dividir_documento(caminho: Path, tamanho_trecho: int = 1500, sobreposicao: int = 200) -> list[Trecho]:
    """Divide um documento .md em trechos (RF25 e RF26)."""
    texto = caminho.read_text(encoding="utf-8")
    trechos: list[Trecho] = []
    for grupo in _unidades(texto):
        for unidade in _juntar_pequenas(grupo):
            cabecalho = unidade.secao
            limite = max(tamanho_trecho - len(cabecalho) - 2, 100)
            for pedaco in _dividir_corpo(unidade.corpo, limite, sobreposicao):
                trechos.append(Trecho(caminho.name, unidade.secao, len(trechos), f"{cabecalho}\n\n{pedaco}"))
    return trechos


def dividir_pasta(pasta: Path = PASTA_PADRAO, tamanho_trecho: int = 1500, sobreposicao: int = 200) -> list[Trecho]:
    """Todos os trechos de todos os documentos .md da pasta, em ordem."""
    return [t for doc in sorted(pasta.glob("*.md")) for t in dividir_documento(doc, tamanho_trecho, sobreposicao)]
