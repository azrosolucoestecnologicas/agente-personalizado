"""Leitura e validação do config.yaml.

Todas as mensagens de erro são em português e dizem:
qual campo, o que está errado e como corrigir.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agente.segredos import tem_chave

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_PADRAO = RAIZ_PROJETO / "config.yaml"

PROVEDORES_ACEITOS = ("openrouter", "anthropic", "openai")
EXTENSOES_LOGO = (".png", ".jpg", ".jpeg", ".svg", ".webp")
PASTA_LOGO = "assets"
TAMANHO_MAX_LOGO = 1024 * 1024  # 1 MB

PADRAO_COR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# Estrutura esperada: nome do campo -> subcampos (dict) ou None (valor final).
ESTRUTURA: dict[str, Any] = {
    "assistente": {"nome": None, "descricao": None},
    "aparencia": {"cor_principal": None, "cor_secundaria": None, "logo": None, "logo_altura": None},
    "ia": {
        "provedores": None,
        "max_tokens": None,
        "temperatura": None,
        "tempo_limite_segundos": None,
        "max_caracteres_pergunta": None,
        "max_mensagens_historico": None,
    },
    "comportamento": {"instrucoes": None},
    "exemplos": None,
}
CAMPOS_PROVEDOR = ("nome", "modelo")


class ErroConfig(Exception):
    """O config.yaml tem um ou mais problemas."""

    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("\n".join(erros))


@dataclass(frozen=True)
class Provedor:
    nome: str
    modelo: str


@dataclass(frozen=True)
class Config:
    nome: str
    descricao: str
    cor_principal: str
    cor_secundaria: str
    logo: Path
    logo_altura: int
    provedores: list[Provedor]
    max_tokens: int
    temperatura: float
    tempo_limite_segundos: int
    max_caracteres_pergunta: int
    max_mensagens_historico: int
    instrucoes: str
    exemplos: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ leitura


def ler_yaml(caminho: Path) -> Any:
    """Lê o arquivo YAML. Levanta ErroConfig com a linha do problema (T1)."""
    if not caminho.is_file():
        raise ErroConfig([f"❌ O arquivo {caminho.name} não foi encontrado. Ele precisa ficar na raiz do projeto."])
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ErroConfig([f"❌ {caminho.name} não está em UTF-8. Salve o arquivo com codificação UTF-8."]) from None
    try:
        return yaml.safe_load(texto)
    except yaml.YAMLError as erro:
        marca = getattr(erro, "problem_mark", None)
        onde = f" na linha {marca.line + 1}, coluna {marca.column + 1}" if marca else ""
        detalhe = getattr(erro, "problem", None) or str(erro)
        dica = "Use 2 espaços para recuar (nunca TAB) e coloque entre aspas textos que tenham ':' ou '#'."
        if "\t" in texto:
            dica = "O arquivo tem caracteres TAB. Troque cada TAB por 2 espaços."
        raise ErroConfig([f"❌ YAML inválido{onde}: {detalhe}. {dica}"]) from None


def carregar_config(caminho: Path | str = ARQUIVO_PADRAO) -> Config:
    """Lê e valida o config.yaml. Levanta ErroConfig com todos os problemas encontrados."""
    caminho = Path(caminho)
    dados = ler_yaml(caminho)
    erros = validar(dados, caminho.resolve().parent)
    if erros:
        raise ErroConfig(erros)
    return _montar(dados, caminho.resolve().parent)


# ---------------------------------------------------------------- validação


def validar(dados: Any, raiz: Path) -> list[str]:
    """Devolve a lista de erros (vazia se estiver tudo certo)."""
    if dados is None:
        return ["❌ O config.yaml está vazio. Copie o modelo da spec (seção 4.1) e preencha."]
    if not isinstance(dados, dict):
        return ["❌ O config.yaml deve começar com campos no formato 'nome: valor' (ex.: 'assistente:')."]

    erros: list[str] = []
    erros += _campos_desconhecidos(dados, ESTRUTURA, "")
    erros += _chaves_no_config(dados, "")

    assistente = _secao(dados, "assistente", erros)
    aparencia = _secao(dados, "aparencia", erros)
    ia = _secao(dados, "ia", erros)
    comportamento = _secao(dados, "comportamento", erros)

    # assistente
    _texto(assistente, "assistente.nome", obrigatorio=True, minimo=1, maximo=60, erros=erros)
    _texto(assistente, "assistente.descricao", obrigatorio=True, minimo=1, maximo=200, erros=erros)

    # aparencia
    _cor(aparencia, "aparencia.cor_principal", obrigatorio=True, erros=erros)
    _cor(aparencia, "aparencia.cor_secundaria", obrigatorio=False, erros=erros)
    _logo(aparencia, raiz, erros)
    _inteiro(aparencia, "aparencia.logo_altura", 24, 300, erros)

    # ia
    _provedores(ia, erros)
    _inteiro(ia, "ia.max_tokens", 64, 8192, erros)
    _numero(ia, "ia.temperatura", 0.0, 1.0, erros)
    _inteiro(ia, "ia.tempo_limite_segundos", 5, 120, erros)
    _inteiro(ia, "ia.max_caracteres_pergunta", 100, 8000, erros)
    _inteiro(ia, "ia.max_mensagens_historico", 0, 50, erros)

    # comportamento
    _texto(comportamento, "comportamento.instrucoes", obrigatorio=True, minimo=20, maximo=8000, erros=erros)

    # exemplos
    _exemplos(dados, erros)
    return erros


def _secao(dados: dict, nome: str, erros: list[str]) -> dict:
    valor = dados.get(nome)
    if valor is None:
        erros.append(f"❌ `{nome}`: seção obrigatória ausente. Adicione a linha '{nome}:' e os campos dela.")
        return {}
    if not isinstance(valor, dict):
        erros.append(f"❌ `{nome}`: deve conter campos recuados abaixo dele (2 espaços), não um valor direto.")
        return {}
    return valor


def _campos_desconhecidos(dados: dict, estrutura: dict, prefixo: str) -> list[str]:
    erros = []
    for chave, valor in dados.items():
        caminho = f"{prefixo}{chave}"
        if chave not in estrutura:
            sugestao = difflib.get_close_matches(str(chave), [str(k) for k in estrutura], n=1, cutoff=0.6)
            dica = f" Você quis dizer `{prefixo}{sugestao[0]}`?" if sugestao else ""
            permitidos = ", ".join(estrutura)
            erros.append(f"❌ `{caminho}`: campo desconhecido.{dica} Campos aceitos aqui: {permitidos}.")
        elif isinstance(estrutura[chave], dict) and isinstance(valor, dict):
            erros += _campos_desconhecidos(valor, estrutura[chave], f"{caminho}.")
    return erros


def _chaves_no_config(valor: Any, caminho: str) -> list[str]:
    """Nenhum valor pode ter cara de chave de API."""
    if isinstance(valor, dict):
        return [e for k, v in valor.items() for e in _chaves_no_config(v, f"{caminho}{k}.")]
    if isinstance(valor, list):
        return [e for i, v in enumerate(valor) for e in _chaves_no_config(v, f"{caminho[:-1]}[{i}].")]
    if isinstance(valor, str) and tem_chave(valor):
        return [
            f"❌ `{caminho[:-1]}`: parece conter uma chave de API. Chaves NUNCA vão no config.yaml: "
            "apague-a daqui, revogue-a no provedor e cadastre uma nova só nos secrets do Hugging Face."
        ]
    return []


def _vazio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _texto(secao: dict, campo: str, obrigatorio: bool, minimo: int, maximo: int, erros: list[str]) -> None:
    valor = secao.get(campo.split(".")[-1])
    if _vazio(valor):
        if obrigatorio:
            erros.append(f"❌ `{campo}`: campo obrigatório vazio ou ausente. Preencha com um texto.")
        return
    if not isinstance(valor, str):
        erros.append(f"❌ `{campo}`: deve ser um texto. Coloque o valor entre aspas.")
        return
    tamanho = len(valor.strip())
    if not minimo <= tamanho <= maximo:
        erros.append(f"❌ `{campo}`: tem {tamanho} caracteres; o permitido é de {minimo} a {maximo}.")


def _cor(secao: dict, campo: str, obrigatorio: bool, erros: list[str]) -> None:
    chave = campo.split(".")[-1]
    valor = secao.get(chave)
    if _vazio(valor):
        if obrigatorio or chave in secao:
            # Sem aspas, '#0F2540' vira comentário no YAML e o valor fica vazio.
            erros.append(
                f'❌ `{campo}`: cor vazia ou ausente. Escreva a cor ENTRE ASPAS, por exemplo "#0F2540" '
                "(sem aspas o '#' é lido como comentário)."
            )
        return
    if not isinstance(valor, str) or not PADRAO_COR.match(valor.strip()):
        erros.append(
            f'❌ `{campo}`: "{valor}" não é uma cor válida. Use o formato #RRGGBB com letras de A a F '
            'e números de 0 a 9, por exemplo "#0F2540".'
        )


def _logo(secao: dict, raiz: Path, erros: list[str]) -> None:
    campo = "aparencia.logo"
    valor = secao.get("logo")
    if _vazio(valor):
        erros.append(f'❌ `{campo}`: campo obrigatório. Informe o caminho da logo, por exemplo "assets/logo.png".')
        return
    if not isinstance(valor, str):
        erros.append(f'❌ `{campo}`: deve ser um texto com o caminho do arquivo, por exemplo "assets/logo.png".')
        return
    relativo = Path(valor.strip())
    if relativo.is_absolute() or relativo.parts[:1] != (PASTA_LOGO,) or ".." in relativo.parts:
        erros.append(
            f"❌ `{campo}`: a logo precisa ficar dentro da pasta '{PASTA_LOGO}/', por exemplo \"assets/logo.png\"."
        )
        return
    if relativo.suffix.lower() not in EXTENSOES_LOGO:
        erros.append(
            f"❌ `{campo}`: extensão '{relativo.suffix or '(nenhuma)'}' não aceita. Use: {', '.join(EXTENSOES_LOGO)}."
        )
        return
    arquivo = raiz / relativo
    # Confere o nome exato (maiúsculas contam no servidor do Hugging Face).
    existentes = [p.name for p in arquivo.parent.iterdir()] if arquivo.parent.is_dir() else []
    if relativo.name not in existentes:
        parecidos = difflib.get_close_matches(relativo.name, existentes, n=1, cutoff=0.5)
        dica = (
            f' Existe "{relativo.parent.as_posix()}/{parecidos[0]}"; confira maiúsculas e minúsculas.'
            if parecidos
            else ""
        )
        erros.append(
            f'❌ `{campo}`: arquivo "{relativo.as_posix()}" não encontrado.{dica} Envie a imagem para a pasta assets/.'
        )
        return
    tamanho = arquivo.stat().st_size
    if tamanho > TAMANHO_MAX_LOGO:
        erros.append(f"❌ `{campo}`: a logo tem {tamanho / 1024 / 1024:.1f} MB; o máximo é 1 MB. Reduza a imagem.")


def _eh_inteiro(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _inteiro(secao: dict, campo: str, minimo: int, maximo: int, erros: list[str]) -> None:
    valor = secao.get(campo.split(".")[-1])
    if valor is None:
        return  # opcional: usa o padrão
    if not _eh_inteiro(valor):
        erros.append(
            f'❌ `{campo}`: "{valor}" não é um número inteiro. Use um número de {minimo} a {maximo}, sem aspas.'
        )
    elif not minimo <= valor <= maximo:
        erros.append(f"❌ `{campo}`: {valor} está fora do permitido. Use um número de {minimo} a {maximo}.")


def _numero(secao: dict, campo: str, minimo: float, maximo: float, erros: list[str]) -> None:
    valor = secao.get(campo.split(".")[-1])
    if valor is None:
        return
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        erros.append(
            f'❌ `{campo}`: "{valor}" não é um número. Use um valor de {minimo} a {maximo} com ponto (ex.: 0.5).'
        )
    elif not minimo <= valor <= maximo:
        erros.append(f"❌ `{campo}`: {valor} está fora do permitido. Use um valor de {minimo} a {maximo}.")


def _provedores(ia: dict, erros: list[str]) -> None:
    campo = "ia.provedores"
    lista = ia.get("provedores")
    if lista is None or lista == []:
        erros.append(f"❌ `{campo}`: informe pelo menos 1 provedor (openrouter, anthropic ou openai).")
        return
    if not isinstance(lista, list):
        erros.append(f"❌ `{campo}`: deve ser uma lista; cada item começa com '- nome: ...'.")
        return
    if len(lista) > 3:
        erros.append(f"❌ `{campo}`: tem {len(lista)} itens; o máximo é 3 (um por provedor).")
    vistos: set[str] = set()
    for i, item in enumerate(lista):
        onde = f"{campo}[{i + 1}]"
        if not isinstance(item, dict):
            erros.append(f"❌ `{onde}`: cada provedor precisa de 'nome' e 'modelo', por exemplo '- nome: openrouter'.")
            continue
        for chave in item:
            if chave not in CAMPOS_PROVEDOR:
                sugestao = difflib.get_close_matches(str(chave), CAMPOS_PROVEDOR, n=1, cutoff=0.6)
                dica = f" Você quis dizer `{sugestao[0]}`?" if sugestao else ""
                erros.append(f"❌ `{onde}.{chave}`: campo desconhecido.{dica} Use apenas 'nome' e 'modelo'.")
        nome = item.get("nome")
        if _vazio(nome):
            erros.append(f"❌ `{onde}.nome`: obrigatório. Use openrouter, anthropic ou openai.")
        elif not isinstance(nome, str) or nome.strip() not in PROVEDORES_ACEITOS:
            sugestao = difflib.get_close_matches(str(nome).strip().lower(), PROVEDORES_ACEITOS, n=1, cutoff=0.5)
            dica = f" Você quis dizer '{sugestao[0]}'?" if sugestao else ""
            erros.append(
                f'❌ `{onde}.nome`: "{nome}" não é aceito.{dica} Use openrouter, anthropic ou openai (minúsculas).'
            )
        elif nome.strip() in vistos:
            erros.append(
                f'❌ `{onde}.nome`: "{nome}" aparece mais de uma vez. Cada provedor só pode ser listado uma vez.'
            )
        else:
            vistos.add(nome.strip())
        modelo = item.get("modelo")
        if _vazio(modelo):
            erros.append(f'❌ `{onde}.modelo`: obrigatório. Informe o ID do modelo, por exemplo "claude-haiku-4-5".')
        elif not isinstance(modelo, str):
            erros.append(f"❌ `{onde}.modelo`: deve ser um texto. Coloque o ID do modelo entre aspas.")


def _exemplos(dados: dict, erros: list[str]) -> None:
    campo = "exemplos"
    lista = dados.get("exemplos")
    if lista is None:
        return
    if not isinstance(lista, list):
        erros.append(f"❌ `{campo}`: deve ser uma lista; cada pergunta começa com '- '.")
        return
    if len(lista) > 6:
        erros.append(f"❌ `{campo}`: tem {len(lista)} perguntas; o máximo é 6.")
    for i, texto in enumerate(lista):
        onde = f"{campo}[{i + 1}]"
        if _vazio(texto):
            erros.append(f"❌ `{onde}`: pergunta vazia. Escreva a pergunta ou apague a linha.")
        elif not isinstance(texto, str):
            erros.append(f"❌ `{onde}`: deve ser um texto. Coloque a pergunta entre aspas.")
        elif len(texto.strip()) > 150:
            erros.append(f"❌ `{onde}`: tem {len(texto.strip())} caracteres; o máximo é 150.")


# ------------------------------------------------------------------ montagem


def _montar(dados: dict, raiz: Path) -> Config:
    """Converte o YAML já validado em Config, aplicando os valores padrão."""
    a, ap, ia, c = dados["assistente"], dados["aparencia"], dados["ia"], dados["comportamento"]
    cor_principal = ap["cor_principal"].strip()
    return Config(
        nome=a["nome"].strip(),
        descricao=a["descricao"].strip(),
        cor_principal=cor_principal,
        cor_secundaria=(ap.get("cor_secundaria") or cor_principal).strip(),
        logo=raiz / ap["logo"].strip(),
        logo_altura=ap.get("logo_altura") or 80,
        provedores=[Provedor(p["nome"].strip(), p["modelo"].strip()) for p in ia["provedores"]],
        max_tokens=ia.get("max_tokens") or 1024,
        temperatura=float(ia["temperatura"]) if ia.get("temperatura") is not None else 0.5,
        tempo_limite_segundos=ia.get("tempo_limite_segundos") or 30,
        max_caracteres_pergunta=ia.get("max_caracteres_pergunta") or 2000,
        max_mensagens_historico=(
            ia["max_mensagens_historico"] if ia.get("max_mensagens_historico") is not None else 10
        ),
        instrucoes=c["instrucoes"].strip(),
        exemplos=[e.strip() for e in dados.get("exemplos") or []],
    )
