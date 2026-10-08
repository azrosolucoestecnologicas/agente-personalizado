"""Testes do portão T21: perguntas_teste.yaml (spec da Parte 2, seção 9)."""

from __future__ import annotations

import copy
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agente.perguntas import ARQUIVO_PADRAO, ErroPerguntas, carregar, normalizar, secao_confere, validar

RAIZ = Path(__file__).resolve().parent.parent

BASE = {
    "limiar_hit_rate": 0.8,
    "top_k": 3,
    "perguntas": [
        {"pergunta": f"Pergunta número {i}?", "fonte_esperada": "parte2-rag.md", "secao_esperada": "RRF"}
        for i in range(5)
    ],
}


def erros(dados) -> str:
    return "\n".join(validar(dados))


def com_pergunta(**campos) -> dict:
    dados = copy.deepcopy(BASE)
    dados["perguntas"][0].update(campos)
    return dados


# ---------------------------------------------------- arquivo do projeto


def test_t21_arquivo_do_projeto_valido():
    conjunto = carregar()
    assert len(conjunto.perguntas) == 12
    assert conjunto.top_k == 3 and conjunto.limiar_hit_rate == 0.8
    fontes = {p.fonte_esperada for p in conjunto.perguntas}
    assert fontes == {"parte1-cicd-deploy.md", "parte2-rag.md"}


def test_t21_perguntas_impossiveis_comentadas_sao_validas_e_derrubam_o_limiar():
    """Descomentar as perguntas impossíveis precisa dar um arquivo válido E um hit rate abaixo do limiar."""
    texto = re.sub(
        r"^  # (- pergunta:|  fonte_esperada:|  secao_esperada:)",
        r"  \1",
        ARQUIVO_PADRAO.read_text("utf-8"),
        flags=re.M,
    )
    dados = yaml.safe_load(texto)
    assert validar(dados) == []
    impossiveis = len(dados["perguntas"]) - 12
    assert impossiveis >= 4
    melhor_caso = 12 / len(dados["perguntas"])  # mesmo acertando todas as reais
    assert melhor_caso < dados["limiar_hit_rate"]


def test_t21_script_ok():
    resultado = subprocess.run(
        [sys.executable, "scripts/validar_perguntas.py"], cwd=RAIZ, capture_output=True, text=True
    )
    assert resultado.returncode == 0, resultado.stdout
    assert "12 perguntas" in resultado.stdout


# ------------------------------------------------------------- formato


def test_t21_base_valida():
    assert validar(BASE) == []


@pytest.mark.parametrize("limiar", [-0.1, 1.5, "80%", None, True])
def test_t21_limiar_invalido(limiar):
    assert "`limiar_hit_rate` deve ser um número de 0 a 1" in erros({**BASE, "limiar_hit_rate": limiar})


@pytest.mark.parametrize("top_k", [0, 11, 2.5, "3", None])
def test_t21_top_k_invalido(top_k):
    assert "`top_k` deve ser um número inteiro de 1 a 10" in erros({**BASE, "top_k": top_k})


def test_t21_minimo_de_perguntas():
    assert "o mínimo é 5" in erros({**BASE, "perguntas": BASE["perguntas"][:3]})


def test_t21_perguntas_nao_e_lista():
    assert "`perguntas` deve ser uma lista" in erros({**BASE, "perguntas": "uma pergunta"})


def test_t21_campo_desconhecido_com_sugestao():
    assert "Você quis dizer `limiar_hit_rate`?" in erros({**BASE, "limiar_hitrate": 0.8})
    assert "Você quis dizer `secao_esperada`?" in erros(com_pergunta(secao_esperado="RRF"))


def test_t21_pergunta_vazia_ou_repetida():
    assert "`pergunta` deve ser um texto" in erros(com_pergunta(pergunta=""))
    dados = copy.deepcopy(BASE)
    dados["perguntas"][1]["pergunta"] = "  PERGUNTA número 0?  "
    assert "está repetida" in erros(dados)


# ----------------------------------------------- fonte e seção existem


def test_t21_fonte_inexistente_com_sugestao():
    texto = erros(com_pergunta(fonte_esperada="parte2-rag.pdf"))
    assert 'o arquivo "parte2-rag.pdf" não existe em documentos/' in texto
    assert 'Você quis dizer "parte2-rag.md"?' in texto


def test_t21_secao_inexistente_com_sugestao():
    texto = erros(com_pergunta(secao_esperada="Recuperacao hibrida e RFF"))
    assert "nenhuma seção de parte2-rag.md contém" in texto
    assert "Título parecido" in texto


def test_t21_secao_sem_acento_e_minuscula_confere():
    assert validar(com_pergunta(secao_esperada="recuperacao HIBRIDA")) == []


def test_t21_subsecao_tambem_conta():
    assert (
        validar(com_pergunta(secao_esperada="O segredo fica com quem executa", fonte_esperada="parte1-cicd-deploy.md"))
        == []
    )


def test_t21_campos_obrigatorios():
    assert "`fonte_esperada` é obrigatória" in erros(com_pergunta(fonte_esperada=None))
    assert "`secao_esperada` é obrigatória" in erros(com_pergunta(secao_esperada=" "))


# ------------------------------------------------------- arquivo em disco


def test_carregar_arquivo_inexistente(tmp_path):
    with pytest.raises(ErroPerguntas, match="não foi encontrado"):
        carregar(tmp_path / "perguntas_teste.yaml")


def test_carregar_yaml_quebrado(tmp_path):
    arquivo = tmp_path / "perguntas_teste.yaml"
    arquivo.write_text('top_k: 3\nperguntas:\n  - pergunta: "sem fechar\n', encoding="utf-8")
    with pytest.raises(ErroPerguntas, match="YAML inválido"):
        carregar(arquivo)


# ------------------------------------------------------------ comparação


def test_normalizar_e_secao_confere():
    assert normalizar("  Recuperação   Híbrida ") == "recuperacao hibrida"
    assert secao_confere("12 Recuperação híbrida e RRF > RRF: Reciprocal Rank Fusion", "rrf")
    assert not secao_confere("09 Chunking: dividir para achar", "RRF")
