"""perguntas_teste.yaml: o golden set que o portão da busca usa (spec da Parte 2, seção 9).

A validação (T21) roda sem rede: confere o formato e se cada fonte e seção
esperadas existem de verdade em documentos/. A avaliação em si (T25) roda
depois, no job "avaliar", contra o banco.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agente.config import RAIZ_PROJETO
from agente.documentos import PASTA_PADRAO, ler_titulos

ARQUIVO_PADRAO = RAIZ_PROJETO / "perguntas_teste.yaml"
MINIMO_PERGUNTAS = 5
CAMPOS_RAIZ = ("limiar_hit_rate", "top_k", "perguntas", "fora_do_material")
CAMPOS_PERGUNTA = ("pergunta", "fonte_esperada", "secao_esperada")


class ErroPerguntas(Exception):
    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("\n".join(erros))


@dataclass(frozen=True)
class PerguntaTeste:
    pergunta: str
    fonte_esperada: str
    secao_esperada: str


@dataclass(frozen=True)
class ConjuntoTeste:
    limiar_hit_rate: float
    top_k: int
    perguntas: list[PerguntaTeste]
    # Perguntas cuja resposta NÃO está no material. Não contam no hit rate:
    # servem para calibrar a similaridade_minima (devem ficar abaixo dela).
    fora_do_material: list[str] = field(default_factory=list)


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaços simples: "Seção  Á" -> "secao a"."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def secao_confere(secao_do_trecho: str, secao_esperada: str) -> bool:
    """A seção do trecho contém o texto esperado? (sem diferenciar maiúsculas e acentos)"""
    return normalizar(secao_esperada) in normalizar(secao_do_trecho)


def _titulos_por_documento(pasta: Path) -> dict[str, list[str]]:
    titulos = {}
    for documento in sorted(pasta.glob("*.md")):
        try:
            texto = documento.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # o T19 já acusa esse problema
        titulos[documento.name] = [t.texto for t in ler_titulos(texto) if t.nivel >= 2]
    return titulos


def _numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def validar(dados: Any, pasta: Path = PASTA_PADRAO) -> list[str]:
    """T21: devolve a lista de erros (vazia = tudo certo)."""
    nome = "perguntas_teste.yaml"
    if not isinstance(dados, dict):
        return [f"❌ {nome}: deve ter os campos limiar_hit_rate, top_k e perguntas."]
    erros: list[str] = []
    for chave in dados:
        if chave not in CAMPOS_RAIZ:
            sugestao = difflib.get_close_matches(str(chave), CAMPOS_RAIZ, n=1, cutoff=0.6)
            dica = f" Você quis dizer `{sugestao[0]}`?" if sugestao else ""
            erros.append(f"❌ {nome}: campo desconhecido `{chave}`.{dica}")

    limiar = dados.get("limiar_hit_rate")
    if not _numero(limiar) or not 0 <= limiar <= 1:
        erros.append(f"❌ {nome}: `limiar_hit_rate` deve ser um número de 0 a 1, por exemplo 0.80 (veio: {limiar}).")
    top_k = dados.get("top_k")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 10:
        erros.append(f"❌ {nome}: `top_k` deve ser um número inteiro de 1 a 10, por exemplo 3 (veio: {top_k}).")

    perguntas = dados.get("perguntas")
    if not isinstance(perguntas, list):
        return erros + [f"❌ {nome}: `perguntas` deve ser uma lista; cada item começa com '- pergunta: ...'."]
    if len(perguntas) < MINIMO_PERGUNTAS:
        erros.append(
            f"❌ {nome}: tem {len(perguntas)} pergunta(s); o mínimo é {MINIMO_PERGUNTAS}. "
            "Com poucas perguntas, uma só muda demais a taxa de acerto."
        )

    fora = dados.get("fora_do_material", [])
    if not isinstance(fora, list) or not all(isinstance(f, str) and 5 <= len(f.strip()) <= 300 for f in fora):
        erros.append(
            f"❌ {nome}: `fora_do_material` deve ser uma lista de perguntas (textos de 5 a 300 caracteres), "
            "cada uma começando com '- '."
        )

    titulos = _titulos_por_documento(pasta)
    vistas: set[str] = set()
    for numero, item in enumerate(perguntas, start=1):
        onde = f"{nome}, pergunta {numero}"
        if not isinstance(item, dict):
            erros.append(f"❌ {onde}: precisa dos campos pergunta, fonte_esperada e secao_esperada.")
            continue
        for chave in item:
            if chave not in CAMPOS_PERGUNTA:
                sugestao = difflib.get_close_matches(str(chave), CAMPOS_PERGUNTA, n=1, cutoff=0.6)
                dica = f" Você quis dizer `{sugestao[0]}`?" if sugestao else ""
                erros.append(f"❌ {onde}: campo desconhecido `{chave}`.{dica}")
        texto = item.get("pergunta")
        if not isinstance(texto, str) or not 5 <= len(texto.strip()) <= 300:
            erros.append(f"❌ {onde}: `pergunta` deve ser um texto de 5 a 300 caracteres.")
        elif normalizar(texto) in vistas:
            erros.append(f'❌ {onde}: a pergunta "{texto.strip()}" está repetida.')
        else:
            vistas.add(normalizar(texto))

        fonte = item.get("fonte_esperada")
        if not isinstance(fonte, str) or not fonte.strip():
            erros.append(f"❌ {onde}: `fonte_esperada` é obrigatória (o nome do arquivo em documentos/).")
            continue
        fonte = fonte.strip()
        if fonte not in titulos:
            sugestao = difflib.get_close_matches(fonte, list(titulos), n=1, cutoff=0.5)
            dica = f' Você quis dizer "{sugestao[0]}"?' if sugestao else ""
            erros.append(f'❌ {onde}: o arquivo "{fonte}" não existe em documentos/.{dica}')
            continue

        secao = item.get("secao_esperada")
        if not isinstance(secao, str) or not secao.strip():
            erros.append(f"❌ {onde}: `secao_esperada` é obrigatória (um pedaço do título da seção).")
            continue
        if not any(secao_confere(t, secao) for t in titulos[fonte]):
            parecidos = difflib.get_close_matches(secao, titulos[fonte], n=1, cutoff=0.4)
            dica = f' Título parecido: "{parecidos[0]}".' if parecidos else ""
            erros.append(f'❌ {onde}: nenhuma seção de {fonte} contém "{secao.strip()}".{dica}')
    return erros


def carregar(caminho: Path | str = ARQUIVO_PADRAO, pasta: Path = PASTA_PADRAO) -> ConjuntoTeste:
    """Lê e valida o arquivo. Levanta ErroPerguntas com todos os problemas."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroPerguntas([f"❌ O arquivo {caminho.name} não foi encontrado na raiz do projeto."])
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except yaml.YAMLError as erro:
        marca = getattr(erro, "problem_mark", None)
        onde = f" na linha {marca.line + 1}" if marca else ""
        raise ErroPerguntas(
            [f"❌ {caminho.name}: YAML inválido{onde}. Use 2 espaços para recuar e aspas nas perguntas."]
        ) from None
    erros = validar(dados, pasta)
    if erros:
        raise ErroPerguntas(erros)
    return ConjuntoTeste(
        limiar_hit_rate=float(dados["limiar_hit_rate"]),
        top_k=dados["top_k"],
        perguntas=[
            PerguntaTeste(p["pergunta"].strip(), p["fonte_esperada"].strip(), p["secao_esperada"].strip())
            for p in dados["perguntas"]
        ],
        fora_do_material=[f.strip() for f in dados.get("fora_do_material", [])],
    )
