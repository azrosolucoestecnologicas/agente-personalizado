"""T24: o supabase/esquema.sql tem a dimensão certa e permissões de menor privilégio.

Roda sem rede, lendo o arquivo. Se alguém abrir demais uma permissão
(por exemplo, deixar a chave publicável promover a coleção), o job
"testes" fica vermelho antes de qualquer publicação.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agente.config import DIMENSAO_EMBEDDING, MODELOS_EMBEDDING, carregar_config

ESQUEMA = Path(__file__).resolve().parent.parent / "supabase" / "esquema.sql"
SQL = ESQUEMA.read_text(encoding="utf-8")
# Sem comentários, para um "-- grant ..." explicativo não contar como permissão.
CODIGO = re.sub(r"--[^\n]*", "", SQL)
PAPEIS_PUBLICOS = {"public", "anon", "authenticated"}


def _sem_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().lower()


def _comandos(inicio: str) -> list[str]:
    """Todos os comandos (até o ';') que começam com a palavra dada."""
    return [_sem_espacos(c) for c in re.findall(rf"\b{inicio}\b[^;]*;", CODIGO, flags=re.IGNORECASE)]


def _papeis(comando: str) -> set[str]:
    destino = re.search(r"\b(?:to|from)\s+(.+?);", comando)
    return {p.strip() for p in destino.group(1).split(",")} if destino else set()


def _funcao(nome: str) -> str:
    m = re.search(rf"create or replace function public\.{nome}\b.*?\$\$.*?\$\$", CODIGO, flags=re.S | re.I)
    assert m, f"função {nome} não encontrada no esquema"
    return m.group(0)


def test_t24_coluna_tem_a_dimensao_do_modelo():
    dimensoes = set(re.findall(r"vector\((\d+)\)", CODIGO))
    assert dimensoes == {str(DIMENSAO_EMBEDDING)}
    assert set(MODELOS_EMBEDDING.values()) == {DIMENSAO_EMBEDDING}


def test_t24_modelo_do_config_cabe_na_coluna():
    modelo = carregar_config().base_conhecimento.modelo_embedding
    assert MODELOS_EMBEDDING[modelo] == DIMENSAO_EMBEDDING


def test_t24_rls_ligada():
    assert "alter table public.trechos enable row level security" in _sem_espacos(CODIGO)


def test_t24_anonimo_so_le_e_so_a_producao():
    grants = [g for g in _comandos("grant") if " on public.trechos " in g]
    assert grants, "o esquema deve dar SELECT na tabela para a chave publicável"
    for grant in grants:
        if _papeis(grant) & PAPEIS_PUBLICOS:
            assert grant.startswith("grant select on"), f"permissão demais para o público: {grant}"
    revogacoes = [r for r in _comandos("revoke") if " on public.trechos " in r]
    assert any({"anon", "authenticated"} <= _papeis(r) for r in revogacoes), "falta tirar a escrita padrão"

    politicas = _sem_espacos(" ".join(re.findall(r"create policy[^;]*;", CODIGO, flags=re.I)))
    assert politicas.count("create policy") == 1, "só uma política: a de leitura"
    assert "for select to anon, authenticated" in politicas
    assert "using (colecao = 'producao')" in politicas


@pytest.mark.parametrize("funcao", ["promover_teste", "limpar_teste"])
def test_t24_anonimo_nao_promove_nem_apaga(funcao):
    revogada = [r for r in _comandos("revoke") if f"function public.{funcao}(" in r]
    assert revogada and PAPEIS_PUBLICOS <= _papeis(revogada[0])
    for grant in (g for g in _comandos("grant") if f"function public.{funcao}(" in g):
        assert _papeis(grant) == {"service_role"}, f"{funcao} liberada demais: {grant}"


def test_t24_anonimo_pode_buscar():
    grants = [g for g in _comandos("grant") if "function public.buscar_hibrido(" in g]
    assert grants and "anon" in _papeis(grants[0])


@pytest.mark.parametrize("funcao", ["buscar_hibrido", "promover_teste", "limpar_teste"])
def test_t24_funcoes_rodam_com_a_permissao_de_quem_chama(funcao):
    corpo = _sem_espacos(_funcao(funcao))
    assert "security invoker" in corpo, "com security definer, a chave publicável passaria por cima da RLS"
    assert "security definer" not in corpo
    assert "set search_path" in corpo


def test_t24_busca_usa_rrf_e_os_dois_jeitos():
    corpo = _sem_espacos(_funcao("buscar_hibrido"))
    assert "rrf_k int default 60" in corpo
    assert "<=>" in corpo and "@@" in corpo
    assert "p_colecao text default 'producao'" in corpo


def test_t24_pode_rodar_de_novo_sem_apagar_dados():
    sql = _sem_espacos(CODIGO)
    assert "create table if not exists public.trechos" in sql
    assert "drop table" not in sql and "truncate" not in sql
    assert "drop policy" not in sql
