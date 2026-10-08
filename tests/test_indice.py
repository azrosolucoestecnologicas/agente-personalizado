"""Tarefa 5 da Parte 2: embeddings, banco, indexação e avaliação (T25).

Tudo sem rede: o Supabase é simulado com httpx.MockTransport ou com um
banco falso em memória, e o modelo de embedding com um gerador falso.
O T25 de verdade roda no job "avaliar", com o banco e o modelo reais.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

from agente.banco import Banco, ErroBanco, Resultado, do_ambiente, vetor_texto
from agente.config import DIMENSAO_EMBEDDING, BaseConhecimento
from agente.embeddings import EmbeddingsFastembed, ErroEmbedding, com_prefixo
from agente.perguntas import ConjuntoTeste, PerguntaTeste, validar

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import avaliar  # noqa: E402
import indexar  # noqa: E402

URL = "https://exemplo.supabase.co"
CHAVE_NOVA = "sb_" + "secret_" + "ChaveDeTesteQueNaoExiste01"
CHAVE_ANTIGA = "eyJ" + "hbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.assinatura"


# ------------------------------------------------------------- embeddings


def test_prefixos_do_e5():
    modelo = "intfloat/multilingual-e5-base"
    assert com_prefixo(modelo, ["oi"], "trecho") == ["passage: oi"]
    assert com_prefixo(modelo, ["oi"], "pergunta") == ["query: oi"]


def test_modelo_sem_prefixo():
    modelo = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    assert com_prefixo(modelo, ["oi"], "pergunta") == ["oi"]


def test_modelo_nao_aceito_e_recusado_antes_de_baixar():
    with pytest.raises(ErroEmbedding, match="não é aceito"):
        EmbeddingsFastembed("modelo/inventado")


def test_e5_small_e_registrado_na_fastembed():
    from fastembed import TextEmbedding

    from agente.embeddings import _registrar

    _registrar("intfloat/multilingual-e5-base")
    _registrar("intfloat/multilingual-e5-base")  # segunda vez não duplica
    registrados = [m for m in TextEmbedding.list_supported_models() if m["model"] == "intfloat/multilingual-e5-base"]
    assert len(registrados) == 1
    assert registrados[0]["dim"] == DIMENSAO_EMBEDDING


# ------------------------------------------------------------------ banco


def banco_simulado(responder, chave=CHAVE_NOVA):
    pedidos = []

    def tratar(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return responder(pedido)

    cliente = httpx.Client(transport=httpx.MockTransport(tratar))
    return Banco(URL, chave, cliente=cliente), pedidos


def test_chave_nova_vai_so_no_apikey():
    banco, pedidos = banco_simulado(lambda p: httpx.Response(200, json=3))
    banco.limpar_teste()
    assert pedidos[0].headers["apikey"] == CHAVE_NOVA
    assert "authorization" not in pedidos[0].headers  # senão o Supabase responde "Invalid JWT"


def test_chave_antiga_vai_nos_dois_cabecalhos():
    banco, pedidos = banco_simulado(lambda p: httpx.Response(200, json=3), chave=CHAVE_ANTIGA)
    banco.limpar_teste()
    assert pedidos[0].headers["authorization"] == f"Bearer {CHAVE_ANTIGA}"


def test_buscar_envia_argumentos_e_le_resultados():
    linha = {
        "id": 7,
        "fonte": "a.md",
        "secao": "S",
        "conteudo": "texto",
        "similaridade": 0.91,
        "nota_rrf": 0.03,
        "pos_palavras": None,
        "pos_sentido": 1,
    }
    banco, pedidos = banco_simulado(lambda p: httpx.Response(200, json=[linha]))
    resultados = banco.buscar("pergunta", [0.5] * DIMENSAO_EMBEDDING, quantidade=3, peso_palavras=0.0, colecao="teste")
    assert pedidos[0].url.path == "/rest/v1/rpc/buscar_hibrido"
    corpo = json.loads(pedidos[0].content)
    assert corpo["p_colecao"] == "teste" and corpo["quantidade"] == 3 and corpo["peso_palavras"] == 0.0
    assert corpo["consulta_embedding"].startswith("[0.5,0.5,")
    assert resultados == [Resultado(7, "a.md", "S", "texto", 0.91, 0.03, None, 1)]


def test_contar_le_o_total_do_cabecalho():
    banco, pedidos = banco_simulado(
        lambda p: httpx.Response(200, json=[{"id": 1}], headers={"content-range": "0-0/124"})
    )
    assert banco.contar("teste") == 124
    assert pedidos[0].url.params["colecao"] == "eq.teste"
    assert pedidos[0].headers["prefer"] == "count=exact"


def test_gravar_em_lotes():
    banco, pedidos = banco_simulado(lambda p: httpx.Response(201))
    linhas = [
        {
            "colecao": "teste",
            "fonte": "a.md",
            "secao": "S",
            "ordem": i,
            "conteudo": "x",
            "embedding": [0.0] * DIMENSAO_EMBEDDING,
        }
        for i in range(120)
    ]
    assert banco.gravar(linhas, lote=50) == 120
    assert [len(json.loads(p.content)) for p in pedidos] == [50, 50, 20]
    assert isinstance(json.loads(pedidos[0].content)[0]["embedding"], str)


def test_gravar_recusa_colecao_invalida():
    banco, pedidos = banco_simulado(lambda p: httpx.Response(201))
    with pytest.raises(ErroBanco, match="Coleção inválida"):
        banco.gravar([{"colecao": "outra", "embedding": []}])
    assert not pedidos


@pytest.mark.parametrize(
    "codigo,corpo,trecho",
    [
        (401, {"message": "Invalid API key"}, "chave foi recusada"),
        (403, {"message": "permission denied for function promover_teste"}, "Permissão negada"),
        (404, {"message": "Could not find the function public.buscar_hibrido"}, "esquema.sql"),
        (400, {"message": "expected 768 dimensions, not 384"}, "tamanho que o banco espera"),
        (503, {"message": "upstream"}, "pausado"),
    ],
)
def test_erros_viram_explicacao(codigo, corpo, trecho):
    banco, _ = banco_simulado(lambda p: httpx.Response(codigo, json=corpo))
    with pytest.raises(ErroBanco, match=trecho):
        banco.promover_teste()


def test_erro_nunca_mostra_a_chave():
    banco, _ = banco_simulado(lambda p: httpx.Response(401, json={"message": f"chave {CHAVE_NOVA} inválida"}))
    with pytest.raises(ErroBanco) as erro:
        banco.limpar_teste()
    assert CHAVE_NOVA not in str(erro.value)


def test_sem_conexao():
    def falhar(pedido):
        raise httpx.ConnectError("sem rede")

    banco, _ = banco_simulado(falhar)
    with pytest.raises(ErroBanco, match="Não consegui conectar"):
        banco.contar()


def test_do_ambiente_explica_o_que_falta():
    with pytest.raises(ErroBanco, match="SUPABASE_SECRET_KEY"):
        do_ambiente("SUPABASE_SECRET_KEY", {"SUPABASE_URL": URL})
    with pytest.raises(ErroBanco, match="https://"):
        do_ambiente("SUPABASE_SECRET_KEY", {"SUPABASE_URL": "exemplo.supabase.co", "SUPABASE_SECRET_KEY": "x"})


def test_vetor_texto():
    assert vetor_texto([0.1, -2, 3.25]) == "[0.1,-2,3.25]"


# ----------------------------------------------------- falsos em memória


class GeradorFalso:
    modelo = "intfloat/multilingual-e5-base"

    def __init__(self, falhar=False):
        self.falhar = falhar
        self.perguntas = []

    def trechos(self, textos):
        if self.falhar:
            raise ErroEmbedding("modelo quebrado")
        return [[float(len(t) % 7)] * DIMENSAO_EMBEDDING for t in textos]

    def pergunta(self, texto):
        self.perguntas.append(texto)
        return [0.1] * DIMENSAO_EMBEDDING


class BancoFalso:
    def __init__(self, respostas=None, perder=0):
        self.linhas = [{"colecao": "teste", "fonte": "velho.md"}, {"colecao": "producao", "fonte": "no-ar.md"}]
        self.respostas = respostas or {}
        self.perder = perder  # simula trechos que somem na gravação
        self.chamadas = []
        self.buscas = []

    def limpar_teste(self):
        self.chamadas.append("limpar")
        antes = len(self.linhas)
        self.linhas = [linha for linha in self.linhas if linha["colecao"] != "teste"]
        return antes - len(self.linhas)

    def gravar(self, linhas):
        self.chamadas.append("gravar")
        self.linhas += list(linhas)[self.perder :]
        return len(linhas)

    def contar(self, colecao="producao"):
        return sum(linha["colecao"] == colecao for linha in self.linhas)

    def promover_teste(self):
        self.chamadas.append("promover")
        teste = [linha for linha in self.linhas if linha["colecao"] == "teste"]
        self.linhas = teste + [{**linha, "colecao": "producao"} for linha in teste]
        return len(teste)

    def buscar(self, consulta, embedding, quantidade=4, peso_palavras=1.0, peso_sentido=1.0, colecao="producao"):
        self.buscas.append((consulta, quantidade, peso_palavras, peso_sentido, colecao))
        return self.respostas.get(consulta, [])[:quantidade]


# --------------------------------------------------------------- indexar


def test_indexar_regrava_so_a_colecao_teste():
    banco = BancoFalso()
    relatorio = indexar.indexar(banco, GeradorFalso(), BaseConhecimento())
    assert banco.chamadas == ["limpar", "gravar"]
    novos = [linha for linha in banco.linhas if linha["colecao"] == "teste"]
    assert len(novos) == 124
    assert all(
        linha["modelo"] == GeradorFalso.modelo and len(linha["embedding"]) == DIMENSAO_EMBEDDING for linha in novos
    )
    assert [linha for linha in banco.linhas if linha["colecao"] == "producao"] == [
        {"colecao": "producao", "fonte": "no-ar.md"}
    ]
    assert "124 trechos" in relatorio and "parte2-rag.md | 86" in relatorio


def test_indexar_gera_vetores_antes_de_apagar():
    banco = BancoFalso()
    with pytest.raises(ErroEmbedding):
        indexar.indexar(banco, GeradorFalso(falhar=True), BaseConhecimento())
    assert banco.chamadas == []  # a coleção teste antiga continua lá


def test_indexar_confere_a_contagem():
    with pytest.raises(ErroBanco, match="Rode de novo"):
        indexar.indexar(BancoFalso(perder=1), GeradorFalso(), BaseConhecimento())


def test_promover(capsys):
    banco = BancoFalso()
    assert indexar.main(["--promover"], banco=banco) == 0
    assert banco.chamadas == ["promover"]
    assert "producao agora tem 1 trechos" in capsys.readouterr().out


def test_main_sem_secrets_explica_e_falha(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "resumo.md"))
    assert indexar.main([], gerador=GeradorFalso()) == 1
    saida = capsys.readouterr().out
    assert "SUPABASE_URL" in saida and "producao não foi alterada" in saida
    assert "Não consegui indexar" in (tmp_path / "resumo.md").read_text(encoding="utf-8")


# --------------------------------------------------------------- avaliar


def resultado(fonte, secao, sim, i=1):
    return Resultado(i, fonte, secao, "texto", sim, 0.03, i, i)


def conjunto(perguntas, fora=(), limiar=0.8, top_k=3):
    return ConjuntoTeste(limiar, top_k, [PerguntaTeste(*p) for p in perguntas], list(fora))


ERRADO = resultado("outro.md", "Outra seção", 0.80)


def test_avaliar_acerto_posicao_e_mrr():
    respostas = {
        "p1": [resultado("a.md", "01 Segredos: onde fica", 0.90)],  # 1º
        "p2": [ERRADO, ERRADO, resultado("a.md", "Segredos", 0.85)],  # 3º: ainda no top-3
        "p3": [ERRADO, ERRADO, ERRADO, resultado("a.md", "Segredos", 0.84)],  # 4º: fora do top-3
        "p4": [ERRADO],  # não veio
    }
    perguntas = [(p, "a.md", "segredos") for p in respostas]
    rel = avaliar.avaliar(BancoFalso(respostas), GeradorFalso(), conjunto(perguntas), BaseConhecimento())
    assert [r.posicao for r in rel.respostas] == [1, 3, 4, None]
    assert [r.acertou for r in rel.respostas] == [True, True, False, False]
    assert rel.hit_rate == 0.5
    assert rel.mrr == pytest.approx((1 + 1 / 3) / 4)
    assert not rel.passou


def test_avaliar_usa_a_colecao_e_os_pesos_do_config():
    banco = BancoFalso()
    base = BaseConhecimento(peso_palavras=0.0, peso_sentido=2.0)
    avaliar.avaliar(banco, GeradorFalso(), conjunto([("p", "a.md", "S")], fora=["f"]), base, "teste")
    assert banco.buscas == [("p", 10, 0.0, 2.0, "teste"), ("f", 10, 0.0, 2.0, "teste")]


def test_fonte_certa_com_secao_errada_nao_conta():
    respostas = {"p": [resultado("a.md", "Outra coisa", 0.9)]}
    rel = avaliar.avaliar(
        BancoFalso(respostas), GeradorFalso(), conjunto([("p", "a.md", "Segredos")]), BaseConhecimento()
    )
    assert rel.respostas[0].posicao is None


def test_calibracao_com_grupos_separados():
    respostas = {
        "p1": [resultado("a.md", "S", 0.88)],
        "p2": [resultado("a.md", "S", 0.86)],
        "fora1": [resultado("a.md", "S", 0.79)],
        "fora2": [resultado("a.md", "S", 0.81)],
    }
    c = conjunto([("p1", "a.md", "S"), ("p2", "a.md", "S")], fora=["fora1", "fora2"])
    rel = avaliar.avaliar(BancoFalso(respostas), GeradorFalso(), c, BaseConhecimento(similaridade_minima=0.80))
    texto = "\n".join(avaliar.calibrar(rel))
    assert "similaridade_minima: 0.83" in texto  # meio de 0.81 e 0.86
    assert "**1** de 2 chegariam ao modelo" in texto


def test_calibracao_com_grupos_misturados():
    respostas = {"p1": [resultado("a.md", "S", 0.84)], "fora": [resultado("a.md", "S", 0.86)]}
    c = conjunto([("p1", "a.md", "S")], fora=["fora"])
    rel = avaliar.avaliar(BancoFalso(respostas), GeradorFalso(), c, BaseConhecimento())
    texto = "\n".join(avaliar.calibrar(rel))
    assert "se misturam" in texto and "similaridade_minima: 0.83" in texto


def test_relatorio_mostra_o_que_veio_no_lugar():
    respostas = {"p1": [resultado("a.md", "S", 0.9)], "p2": [ERRADO]}
    c = conjunto([("p1", "a.md", "S"), ("p2", "a.md", "S")])
    texto = avaliar.markdown(avaliar.avaliar(BancoFalso(respostas), GeradorFalso(), c, BaseConhecimento()))
    assert "❌ T25: hit rate@3 = 0.50 (mínimo 0.80)" in texto
    assert "outro.md › Outra seção (0.800)" in texto
    assert "Nada foi publicado" in texto


def test_main_aprova_e_reprova_pelo_limiar(monkeypatch):
    perguntas = [(f"p{i}", "a.md", "S") for i in range(5)]
    monkeypatch.setattr(avaliar, "carregar", lambda: conjunto(perguntas, limiar=0.8))
    acertos = {f"p{i}": [resultado("a.md", "S", 0.9)] for i in range(4)}  # 4 de 5 = 0.80

    banco = BancoFalso(acertos)
    assert avaliar.main([], gerador=GeradorFalso(), banco=banco) == 0

    del acertos["p3"]  # 3 de 5 = 0.60
    assert avaliar.main([], gerador=GeradorFalso(), banco=BancoFalso(acertos)) == 1


def test_main_colecao_vazia(capsys):
    banco = BancoFalso()
    banco.linhas = []
    assert avaliar.main([], gerador=GeradorFalso(), banco=banco) == 1
    assert "rode antes o scripts/indexar.py" in capsys.readouterr().out


# ---------------------------------------------------- perguntas_teste.yaml


def test_fora_do_material_e_opcional_e_validado():
    base = {"limiar_hit_rate": 0.8, "top_k": 3, "perguntas": []}
    assert not any("fora_do_material" in e for e in validar(base))
    erros = validar({**base, "fora_do_material": ["ok, pergunta válida", 3]})
    assert any("fora_do_material" in e for e in erros)


def test_projeto_tem_perguntas_fora_do_material():
    from agente.perguntas import carregar

    assert len(carregar().fora_do_material) >= 5


@pytest.mark.parametrize("script,argv", [(indexar, []), (indexar, ["--promover"]), (avaliar, [])])
def test_base_desligada_nao_toca_no_banco(monkeypatch, capsys, script, argv):
    from agente.config import carregar_config

    config = carregar_config()
    desligada = type(config)(**{**config.__dict__, "base_conhecimento": BaseConhecimento(ativa=False)})
    monkeypatch.setattr(script, "carregar_config", lambda: desligada)
    banco = BancoFalso()
    assert script.main(argv, gerador=GeradorFalso(), banco=banco) == 0
    assert banco.chamadas == [] and banco.buscas == []
    assert "desligada" in capsys.readouterr().out
