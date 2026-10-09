"""Servidor da Parte 3: T26 (contrato da API), T27 (nada de segredo exposto) e T15 (fumaça).

Nada aqui usa rede: busca, modelo e IA são simulados.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agente.banco import ErroBanco
from agente.config import BaseConhecimento, Servidor, carregar_config
from agente.rag import BaseRAG
from agente.servidor import CARREGAR, criar_servidor
from tests.test_rag import BancoFalso, GeradorFalso, trecho
from tests.test_roteador import ErroHttp, ProvedorFalso
from tests.test_segredos import CHAVES_FALSAS

RAIZ = Path(__file__).resolve().parent.parent
NAO_ENCONTREI = "Não encontrei isso no material do curso."


class Relogio:
    def __init__(self, agora: float = 1_800_000_000.0):  # 2027-01-15, 08:00 UTC
        self.agora = agora

    def __call__(self) -> float:
        return self.agora


@pytest.fixture
def config():
    base = carregar_config()
    return replace(base, base_conhecimento=replace(base.base_conhecimento, similaridade_minima=0.84))


def cliente(config, provedores=None, resultados=(), rag="padrao", **kwargs) -> TestClient:
    if rag == "padrao":
        rag = BaseRAG(config.base_conhecimento, BancoFalso(resultados), GeradorFalso())
    provedores = (
        [ProvedorFalso("openrouter", pedacos=["Resposta ", "do modelo."])] if provedores is None else provedores
    )
    return TestClient(criar_servidor(config, provedores=provedores, rag=rag, ambiente={}, **kwargs))


def eventos_sse(resposta) -> list[tuple[str, dict]]:
    """Lê o corpo text/event-stream: [(evento, dados), ...]."""
    saida = []
    for bloco in resposta.text.strip().split("\n\n"):
        linhas = dict(linha.split(": ", 1) for linha in bloco.splitlines())
        saida.append((linhas["event"], json.loads(linhas["data"])))
    return saida


def perguntar(c: TestClient, mensagem="O que é RRF?", **extra):
    return c.post("/api/perguntar", json={"mensagem": mensagem, **extra})


# ------------------------------------------------------- T26: /api/saude


def test_t26_saude_pronto_com_versao_e_trechos(config):
    c = TestClient(
        criar_servidor(
            config,
            provedores=[],
            rag=BaseRAG(config.base_conhecimento, BancoFalso([trecho(1), trecho(2)]), GeradorFalso()),
            ambiente={"RAILWAY_GIT_COMMIT_SHA": "a1b2c3d4e5f6"},
        )
    )
    resposta = c.get("/api/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "versao": "a1b2c3d", "trechos_na_producao": 2}


def test_t26_saude_guarda_a_contagem_por_um_minuto(config):
    banco = BancoFalso([trecho(1)])
    contagens = []
    banco.contar = lambda colecao="producao": contagens.append(colecao) or 1
    c = cliente(config, rag=BaseRAG(config.base_conhecimento, banco, GeradorFalso()))
    c.get("/api/saude")
    c.get("/api/saude")
    assert contagens == ["producao"]


def test_t26_saude_sem_supabase_responde_503(config):
    rag = BaseRAG(config.base_conhecimento, None, None, motivo_indisponivel="Faltam as variáveis SUPABASE_URL")
    resposta = cliente(config, rag=rag).get("/api/saude")
    assert resposta.status_code == 503
    assert resposta.json()["status"] == "indisponivel" and "SUPABASE_URL" in resposta.json()["motivo"]
    assert resposta.json()["versao"] == "local"


def test_t26_saude_banco_fora_do_ar_responde_503(config):
    banco = BancoFalso()

    def falhar(colecao="producao"):
        raise ErroBanco("O Supabase demorou demais para responder")

    banco.contar = falhar
    resposta = cliente(config, rag=BaseRAG(config.base_conhecimento, banco, GeradorFalso())).get("/api/saude")
    assert resposta.status_code == 503 and "demorou demais" in resposta.json()["motivo"]


def test_t26_saude_base_desligada_esta_ok(config):
    desligada = replace(config, base_conhecimento=BaseConhecimento(ativa=False))
    resposta = cliente(desligada, rag=None).get("/api/saude")
    assert resposta.status_code == 200 and resposta.json()["trechos_na_producao"] is None


def test_t26_enquanto_carrega_responde_503(config):
    c = TestClient(criar_servidor(config, provedores=[], rag=CARREGAR, ambiente={}))  # sem "with": não carrega
    assert c.get("/api/saude").json()["status"] == "carregando"
    resposta = perguntar(c)
    assert resposta.status_code == 503 and resposta.json()["erro"] == "carregando"


# ---------------------------------------------------- T26: /api/perguntar


def test_t26_material_fontes_antes_do_texto_e_fim(config):
    c = cliente(config, resultados=[trecho(1, secao="12 RRF"), trecho(2, secao="11 BM25")])
    resposta = perguntar(c)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/event-stream")
    eventos = eventos_sse(resposta)
    assert [e for e, _ in eventos] == ["fontes", "texto", "texto", "fim"]
    fontes = eventos[0][1]["fontes"]
    assert fontes[0] == {"n": 1, "fonte": "parte2-rag.md", "secao": "12 RRF", "trecho": trecho(1).conteudo}
    assert [d["delta"] for e, d in eventos if e == "texto"] == ["Resposta ", "do modelo."]
    assert eventos[-1] == ("fim", {"nao_encontrado": False})
    assert "Fontes consultadas" not in resposta.text  # as fontes vão no evento, não coladas no texto


def test_t26_nada_relevante_frase_exata_sem_chamar_a_ia(config):
    ia = ProvedorFalso("openrouter", pedacos=["inventei"])
    eventos = eventos_sse(perguntar(cliente(config, [ia], [trecho(1, sim=0.5)])))
    assert eventos == [("texto", {"delta": NAO_ENCONTREI}), ("fim", {"nao_encontrado": True})]
    assert ia.chamadas == 0


def test_t26_modelo_respondeu_nao_encontrei(config):
    ia = ProvedorFalso("openrouter", pedacos=[NAO_ENCONTREI])
    eventos = eventos_sse(perguntar(cliente(config, [ia], [trecho(1)])))
    assert eventos[-1] == ("fim", {"nao_encontrado": True})


def test_t26_cumprimento_sem_fontes(config):
    eventos = eventos_sse(perguntar(cliente(config, resultados=[trecho(1)]), "Oi, tudo bem?"))
    assert [e for e, _ in eventos] == ["texto", "texto", "fim"]


def test_t26_todos_os_provedores_falham(config):
    ia = ProvedorFalso("openrouter", erro_antes=ErroHttp(500))
    eventos = eventos_sse(perguntar(cliente(config, [ia], [trecho(1)])))
    assert eventos[-1][0] == "erro" and eventos[-1][1]["tipo"] == "provedores"
    assert "Não consegui responder agora" in eventos[-1][1]["mensagem"]


def test_t26_resposta_interrompida(config):
    ia = ProvedorFalso("openrouter", pedacos=["Começo"], erro_depois=ErroHttp(500))
    eventos = eventos_sse(perguntar(cliente(config, [ia], [trecho(1)])))
    assert [e for e, _ in eventos] == ["fontes", "texto", "erro"]
    assert eventos[-1][1]["tipo"] == "interrompida"


def test_t26_base_indisponivel(config):
    eventos = eventos_sse(perguntar(cliente(config, rag=BaseRAG(config.base_conhecimento, None, None))))
    assert eventos == [("erro", {"tipo": "base_indisponivel", "mensagem": eventos[0][1]["mensagem"]})]


def test_t26_historico_chega_ao_modelo(config):
    ia = ProvedorFalso("openrouter", pedacos=["ok"])
    historico = [{"papel": "usuario", "texto": "O que é deploy?"}, {"papel": "assistente", "texto": "É publicar."}]
    perguntar(cliente(config, [ia], [trecho(1)]), "E o RRF?", historico=historico)
    mensagens = ia.ultimo_pedido.mensagens
    assert mensagens[:2] == [
        {"role": "user", "content": "O que é deploy?"},
        {"role": "assistant", "content": "É publicar."},
    ]


def test_t26_pergunta_longa_413_sem_chamar_a_ia(config):
    ia = ProvedorFalso("openrouter", pedacos=["x"])
    resposta = perguntar(cliente(config, [ia]), "a" * (config.max_caracteres_pergunta + 1))
    assert resposta.status_code == 413
    assert resposta.json()["erro"] == "pergunta_longa" and "limite é 2000" in resposta.json()["mensagem"]
    assert ia.chamadas == 0


@pytest.mark.parametrize(
    "corpo,trecho_esperado",
    [
        ({"mensagem": "   "}, "a pergunta está vazia"),
        ({}, "falta o campo `mensagem`"),
        ({"mensagem": "oi", "modelo": "gpt-5"}, "o campo `modelo` não é aceito"),
        ({"mensagem": "oi", "temperatura": 2}, "o campo `temperatura` não é aceito"),
        ({"mensagem": "oi", "historico": [{"papel": "usuario", "texto": "x"}] * 21}, "no máximo 20 mensagens"),
        ({"mensagem": "oi", "historico": [{"papel": "sistema", "texto": "x"}]}, "'usuario' ou 'assistente'"),
        ({"mensagem": "oi", "historico": [{"papel": "usuario", "texto": "x" * 8001}]}, "passa de 8000"),
    ],
)
def test_t26_pedido_invalido_422_em_portugues(config, corpo, trecho_esperado):
    resposta = cliente(config).post("/api/perguntar", json=corpo)
    assert resposta.status_code == 422
    assert resposta.json()["erro"] == "pedido_invalido" and trecho_esperado in resposta.json()["mensagem"]


def test_t26_json_quebrado_422(config):
    resposta = cliente(config).post(
        "/api/perguntar", content="{mensagem:", headers={"Content-Type": "application/json"}
    )
    assert resposta.status_code == 422 and "JSON válido" in resposta.json()["mensagem"]


# -------------------------------------------------- T26: limite de uso (429)


def test_t26_limite_por_minuto_com_retry_after(config):
    relogio = Relogio()
    c = cliente(config, relogio=relogio)
    assert all(perguntar(c).status_code == 200 for _ in range(10))
    resposta = perguntar(c)
    assert resposta.status_code == 429
    assert resposta.headers["Retry-After"] == "60" and resposta.json()["tentar_em"] == 60
    assert "Tente de novo em 60 segundos" in resposta.json()["mensagem"]
    relogio.agora += 60
    assert perguntar(c).status_code == 200


def test_t26_limite_por_dia_ate_a_meia_noite_utc(config):
    relogio = Relogio()
    c = cliente(replace(config, servidor=Servidor(perguntas_por_minuto=10, perguntas_por_dia=3)), relogio=relogio)
    for _ in range(3):
        assert perguntar(c).status_code == 200
    resposta = perguntar(c)
    assert resposta.status_code == 429 and resposta.json()["tentar_em"] == 16 * 3600  # 08:00 → 24:00
    relogio.agora += 16 * 3600
    assert perguntar(c).status_code == 200


def test_t26_limite_e_por_visitante(config):
    c = cliente(replace(config, servidor=Servidor(perguntas_por_minuto=1, perguntas_por_dia=10)), relogio=Relogio())
    a = {"X-Forwarded-For": "200.150.10.20, 10.0.0.1"}
    b = {"X-Forwarded-For": "189.1.2.3"}
    assert c.post("/api/perguntar", json={"mensagem": "oi"}, headers=a).status_code == 200
    assert c.post("/api/perguntar", json={"mensagem": "oi"}, headers=a).status_code == 429
    assert c.post("/api/perguntar", json={"mensagem": "oi"}, headers=b).status_code == 200


def test_t26_pedido_invalido_ou_longo_nao_gasta_o_limite(config):
    c = cliente(replace(config, servidor=Servidor(perguntas_por_minuto=1, perguntas_por_dia=10)), relogio=Relogio())
    perguntar(c, "   ")
    perguntar(c, "a" * 5000)
    assert perguntar(c).status_code == 200


# ----------------------------------------------- T26: interface e cabeçalhos


def test_t26_rota_desconhecida_da_api_e_404_em_json(config):
    resposta = cliente(config).get("/api/nao-existe")
    assert resposta.status_code == 404 and resposta.json()["erro"] == "nao_encontrado"


def test_t26_sem_interface_compilada_mostra_aviso(config, tmp_path):
    resposta = cliente(config, pasta_interface=tmp_path / "dist").get("/")
    assert resposta.status_code == 200 and "npm run build" in resposta.text


def test_t26_entrega_a_interface_compilada(config, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>chat</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "segredo.txt").write_text("não pode sair", encoding="utf-8")
    c = cliente(config, pasta_interface=dist)
    assert "<title>chat</title>" in c.get("/").text
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert "<title>chat</title>" in c.get("/qualquer/rota").text  # a interface cuida das rotas dela
    assert "não pode sair" not in c.get("/../segredo.txt").text
    assert "não pode sair" not in c.get("/%2e%2e/segredo.txt").text


def test_t26_cabecalhos_de_seguranca(config):
    resposta = cliente(config).get("/api/config")
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
    assert "script-src 'self'" in resposta.headers["Content-Security-Policy"]
    assert resposta.headers["Referrer-Policy"] == "same-origin"


def test_t26_logo(config):
    resposta = cliente(config).get("/api/logo")
    assert resposta.status_code == 200 and resposta.headers["content-type"].startswith("image/svg")


def test_t26_sem_documentacao_automatica_publica(config):
    c = cliente(config)
    assert "swagger" not in c.get("/docs").text.lower()
    assert c.get("/openapi.json").status_code != 200 or "paths" not in c.get("/openapi.json").text


# --------------------------------------------- T27: nada de segredo exposto


def test_t27_config_publico_nao_tem_segredos(config):
    ambiente = {
        "OPENROUTER_API_KEY": CHAVES_FALSAS["chave do OpenRouter"],
        "ANTHROPIC_API_KEY": CHAVES_FALSAS["chave da Anthropic"],
        "OPENAI_API_KEY": CHAVES_FALSAS["chave da OpenAI"],
        "SUPABASE_URL": "https://projetosecreto.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_" + "x" * 30,
    }
    c = TestClient(criar_servidor(config, rag=None, ambiente=ambiente))
    texto = c.get("/api/config").text
    dados = json.loads(texto)
    assert set(dados) == {
        "nome", "descricao", "exemplos", "logo_url", "cores", "limites", "mensagem_nao_encontrado",
    }  # fmt: skip
    proibidos = [*ambiente.values(), config.instrucoes[:40], "instrucoes", "openrouter", "anthropic", "supabase"]
    proibidos += [p.modelo for p in config.provedores]
    for item in proibidos:
        assert item.lower() not in texto.lower(), item


def test_t27_interface_nao_usa_variaveis_de_ambiente():
    """Variáveis VITE_ são copiadas para o JavaScript público. A interface só chama /api relativo."""
    fonte = RAIZ / "frontend" / "src"
    if not fonte.is_dir():
        pytest.skip("a interface chega na tarefa 3")
    for arquivo in fonte.rglob("*"):
        if arquivo.suffix in (".ts", ".tsx", ".js", ".jsx"):
            texto = arquivo.read_text(encoding="utf-8")
            assert "import.meta.env" not in texto and "VITE_" not in texto, arquivo
            assert "openrouter.ai" not in texto and "api.openai.com" not in texto, arquivo


@pytest.mark.parametrize("nome", ["Dockerfile", "railway.json"])
def test_t27_arquivos_de_deploy_sem_chaves(nome):
    from agente.segredos import procurar_em_texto

    arquivo = RAIZ / nome
    if not arquivo.is_file():
        pytest.skip(f"{nome} chega na tarefa 5")
    texto = arquivo.read_text(encoding="utf-8")
    assert procurar_em_texto(texto) == []
    for variavel in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SUPABASE_SECRET_KEY"):
        assert variavel not in texto, f"{nome} não pode mencionar {variavel}: as chaves vêm das Variables"


def test_t27_log_nao_guarda_a_pergunta(config, caplog):
    with caplog.at_level(logging.INFO, logger="agente"):
        perguntar(cliente(config, resultados=[trecho(1)]), "Pergunta muito pessoal sobre o meu CPF")
    assert "pessoal" not in caplog.text
    assert "Pergunta: 38 caracteres · resposta: material" in caplog.text


def test_t27_log_do_limite_mascara_o_ip(config, caplog):
    c = cliente(replace(config, servidor=Servidor(perguntas_por_minuto=1, perguntas_por_dia=5)), relogio=Relogio())
    with caplog.at_level(logging.INFO, logger="agente"):
        for _ in range(2):
            c.post("/api/perguntar", json={"mensagem": "oi"}, headers={"X-Forwarded-For": "200.150.10.20"})
    assert "200.150.x.x" in caplog.text and "200.150.10.20" not in caplog.text


# ---------------------------------------------------- T15: teste de fumaça


def test_t15_servidor_sobe_sem_chaves_e_sem_rede(monkeypatch):
    import importlib
    import sys

    for variavel in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SUPABASE_URL"):
        monkeypatch.delenv(variavel, raising=False)
    sys.modules.pop("agente.servidor", None)
    servidor = importlib.import_module("agente.servidor")  # importar não carrega o modelo nem abre rede
    assert servidor.app.title == carregar_config().nome


def test_t15_sem_chave_o_chat_explica_como_cadastrar(config):
    eventos = eventos_sse(perguntar(cliente(config, provedores=[], resultados=[trecho(1)]), "Oi"))
    assert eventos[0][0] == "erro" and eventos[0][1]["tipo"] == "sem_chave"
    assert "Nenhuma chave de IA configurada" in eventos[0][1]["mensagem"]


def test_t15_config_invalido_impede_o_servidor_de_subir(tmp_path):
    import subprocess
    import sys

    (tmp_path / "config.yaml").write_text("assistente: [", encoding="utf-8")
    codigo = (
        "import agente.config as c, pathlib; c.ARQUIVO_PADRAO = pathlib.Path('config.yaml'); import agente.servidor"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], cwd=tmp_path, capture_output=True, text=True, env={"PYTHONPATH": str(RAIZ)}
    )
    assert resultado.returncode == 1 and "YAML inválido" in resultado.stderr
