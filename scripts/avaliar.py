"""Portão T25: faz as perguntas de teste à busca e compara o hit rate com o limiar.

Uso (no GitHub Actions, depois do indexar.py):
    python scripts/avaliar.py                    # avalia a coleção "teste"
    python scripts/avaliar.py --colecao producao # avalia o que está no ar

Acerto: algum dos top_k primeiros trechos tem a fonte esperada e uma seção
que contém a seção esperada. Hit rate@k = acertos / perguntas (é o que barra).
MRR = média de 1/posição do primeiro trecho certo (0 se não veio): só informa.

O relatório (aba Summary do Actions) também mostra a similaridade dos
trechos certos e das perguntas fora do material, para calibrar a
similaridade_minima do config.yaml.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.banco import COLECOES, Banco, ErroBanco, Resultado, do_ambiente  # noqa: E402
from agente.config import BaseConhecimento, ErroConfig, carregar_config  # noqa: E402
from agente.embeddings import ErroEmbedding, GeradorEmbeddings  # noqa: E402
from agente.perguntas import ConjuntoTeste, ErroPerguntas, PerguntaTeste, carregar, secao_confere  # noqa: E402

CHAVE = "SUPABASE_SECRET_KEY"
PROFUNDIDADE = 10  # busca até 10 trechos, para mostrar a posição mesmo quando passa do top_k


@dataclass(frozen=True)
class Resposta:
    pergunta: PerguntaTeste
    resultados: list[Resultado]
    posicao: int | None  # 1 = primeiro; None = o trecho certo não veio
    top_k: int

    @property
    def acertou(self) -> bool:
        return self.posicao is not None and self.posicao <= self.top_k

    @property
    def certo(self) -> Resultado | None:
        return self.resultados[self.posicao - 1] if self.posicao else None


@dataclass(frozen=True)
class Relatorio:
    respostas: list[Resposta]
    fora: list[tuple[str, float]]  # (pergunta fora do material, maior similaridade que alcançou)
    conjunto: ConjuntoTeste
    base: BaseConhecimento
    colecao: str

    @property
    def hit_rate(self) -> float:
        return sum(r.acertou for r in self.respostas) / len(self.respostas)

    @property
    def mrr(self) -> float:
        return sum(1 / r.posicao for r in self.respostas if r.acertou) / len(self.respostas)

    @property
    def passou(self) -> bool:
        return self.hit_rate >= self.conjunto.limiar_hit_rate


def posicao_certa(pergunta: PerguntaTeste, resultados: list[Resultado]) -> int | None:
    for i, r in enumerate(resultados, start=1):
        if r.fonte == pergunta.fonte_esperada and secao_confere(r.secao, pergunta.secao_esperada):
            return i
    return None


def avaliar(
    banco: Banco, gerador: GeradorEmbeddings, conjunto: ConjuntoTeste, base: BaseConhecimento, colecao: str = "teste"
) -> Relatorio:
    quantidade = max(conjunto.top_k, PROFUNDIDADE)

    def buscar(texto: str) -> list[Resultado]:
        return banco.buscar(
            texto,
            gerador.pergunta(texto),
            quantidade=quantidade,
            peso_palavras=base.peso_palavras,
            peso_sentido=base.peso_sentido,
            colecao=colecao,
        )

    respostas = []
    for pergunta in conjunto.perguntas:
        resultados = buscar(pergunta.pergunta)
        respostas.append(Resposta(pergunta, resultados, posicao_certa(pergunta, resultados), conjunto.top_k))
    fora = []
    for texto in conjunto.fora_do_material:
        resultados = buscar(texto)
        fora.append((texto, max((r.similaridade for r in resultados), default=0.0)))
    return Relatorio(respostas, fora, conjunto, base, colecao)


# ------------------------------------------------------------ calibração


def _baixo(valor: float) -> float:
    return math.floor(valor * 100) / 100


def calibrar(relatorio: Relatorio) -> list[str]:
    """Sugere a similaridade_minima: acima das perguntas fora do material, abaixo dos trechos certos."""
    dentro = [r.certo.similaridade for r in relatorio.respostas if r.acertou]
    fora = [s for _, s in relatorio.fora]
    atual = relatorio.base.similaridade_minima
    linhas = []
    if dentro:
        cortados = sum(s < atual for s in dentro)
        linhas.append(
            f"- Trechos certos: similaridade de **{min(dentro):.3f}** a **{max(dentro):.3f}**. "
            f"Com a similaridade_minima atual ({atual:.2f}), **{cortados}** de {len(dentro)} seriam descartados."
        )
    if fora:
        passam = sum(s >= atual for s in fora)
        linhas.append(
            f"- Perguntas fora do material: maior similaridade de **{min(fora):.3f}** a **{max(fora):.3f}**. "
            f"Com {atual:.2f}, **{passam}** de {len(fora)} chegariam ao modelo (deveriam ser 0)."
        )
    if dentro and fora:
        if max(fora) < min(dentro):
            sugestao = _baixo((max(fora) + min(dentro)) / 2)
            linhas.append(
                f"- **Sugestão: similaridade_minima: {sugestao:.2f}** (no meio do intervalo que separa os dois grupos)."
            )
        else:
            sugestao = _baixo(min(dentro) - 0.005)
            passam = sum(s >= sugestao for s in fora)
            linhas.append(
                f"- Os grupos se misturam. **Sugestão: similaridade_minima: {sugestao:.2f}** (não descarta nenhum "
                f"trecho certo; {passam} pergunta(s) fora do material ainda passariam e o modelo, pelas regras do "
                "prompt, responde que não encontrou)."
            )
    return linhas


# -------------------------------------------------------------- relatório


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def markdown(relatorio: Relatorio) -> str:
    c, b = relatorio.conjunto, relatorio.base
    icone = "✅" if relatorio.passou else "❌"
    acertos = sum(r.acertou for r in relatorio.respostas)
    partes = [
        f"## {icone} T25: hit rate@{c.top_k} = {relatorio.hit_rate:.2f} (mínimo {c.limiar_hit_rate:.2f})",
        "",
        f"{acertos} de {len(relatorio.respostas)} perguntas acertadas · MRR = {relatorio.mrr:.3f} · "
        f"coleção `{relatorio.colecao}` · pesos palavras {b.peso_palavras} / sentido {b.peso_sentido}",
        "",
        "| # | Pergunta | Posição | Similaridade | Palavras / Sentido | Veio em 1º (quando errou) |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(relatorio.respostas, start=1):
        marca = "✅" if r.acertou else "❌"
        if r.certo:
            posicao = f"{marca} {r.posicao}º"
            sim = f"{r.certo.similaridade:.3f}"
            fontes = f"{r.certo.pos_palavras or '—'} / {r.certo.pos_sentido or '—'}"
        else:
            posicao, sim, fontes = f"{marca} não veio", "—", "—"
        primeiro = ""
        if not r.acertou and r.resultados:
            p = r.resultados[0]
            primeiro = f"{p.fonte} › {p.secao} ({p.similaridade:.3f})"
        partes.append(f"| {i} | {_celula(r.pergunta.pergunta)} | {posicao} | {sim} | {fontes} | {_celula(primeiro)} |")
    partes += ["", "**Calibração da similaridade_minima**", ""] + (calibrar(relatorio) or ["- Sem dados."])
    if relatorio.fora:
        partes += ["", "| Fora do material | Maior similaridade |", "|---|---|"]
        partes += [f"| {_celula(t)} | {s:.3f} |" for t, s in relatorio.fora]
    if not relatorio.passou:
        partes += [
            "",
            "**Nada foi publicado:** a coleção producao não foi tocada e o assistente no ar segue como estava. "
            "Veja acima o que veio no lugar de cada pergunta errada e ajuste o documento, o `tamanho_trecho` "
            "ou a pergunta.",
        ]
    return "\n".join(partes)


def escrever_resumo_actions(texto: str) -> None:
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")


def main(argv: list[str] | None = None, gerador: GeradorEmbeddings | None = None, banco: Banco | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia a busca com as perguntas de teste (T25).")
    parser.add_argument("--colecao", choices=COLECOES, default="teste")
    args = parser.parse_args(argv)
    try:
        base = carregar_config().base_conhecimento
        if not base.ativa:
            print("ℹ️ Base de conhecimento desligada no config.yaml (ativa: false): nada a fazer.")
            escrever_resumo_actions("## ℹ️ Base de conhecimento desligada: nada a fazer")
            return 0
        conjunto = carregar()
        banco = banco or do_ambiente(CHAVE)
        if gerador is None:
            from agente.embeddings import EmbeddingsFastembed

            gerador = EmbeddingsFastembed(base.modelo_embedding)
        if banco.contar(args.colecao) == 0:
            raise ErroBanco(f"A coleção {args.colecao} está vazia: rode antes o scripts/indexar.py.")
        relatorio = avaliar(banco, gerador, conjunto, base, args.colecao)
    except ErroPerguntas as erro:
        print("❌ perguntas_teste.yaml tem problemas:\n" + "\n".join(erro.erros))
        return 1
    except (ErroConfig, ErroBanco, ErroEmbedding) as erro:
        print(f"❌ Não consegui avaliar: {erro}")
        escrever_resumo_actions(f"## ❌ Não consegui avaliar\n\n{erro}")
        return 1
    texto = markdown(relatorio)
    print(texto)
    escrever_resumo_actions(texto)
    return 0 if relatorio.passou else 1


if __name__ == "__main__":
    sys.exit(main())
