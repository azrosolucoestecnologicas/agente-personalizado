"""Testes do portão T1–T7: validação do config.yaml."""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agente.config import ARQUIVO_PADRAO, ErroConfig, carregar_config, validar

RAIZ = Path(__file__).resolve().parent.parent

CONFIG_BASE = {
    "assistente": {"nome": "Professor", "descricao": "Tira dúvidas."},
    "aparencia": {"cor_principal": "#0F2540", "logo": "assets/logo.png"},
    "ia": {"provedores": [{"nome": "openrouter", "modelo": "google/gemma-4-31b-it:free"}]},
    "comportamento": {"instrucoes": "Você é um professor didático de dados e IA."},
}


@pytest.fixture
def projeto(tmp_path: Path) -> Path:
    """Pasta temporária com assets/logo.png, como um projeto de verdade."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.png").write_bytes(b"\x89PNG fake")
    return tmp_path


def erros_de(dados, raiz: Path) -> str:
    return "\n".join(validar(dados, raiz))


def com(**alteracoes) -> dict:
    """Cópia do CONFIG_BASE com alterações no formato 'secao__campo=valor'."""
    dados = copy.deepcopy(CONFIG_BASE)
    for chave, valor in alteracoes.items():
        secao, _, campo = chave.partition("__")
        if campo:
            dados[secao][campo] = valor
        else:
            dados[secao] = valor
    return dados


# ------------------------------------------------------------- arquivo real


def test_config_do_projeto_e_valido():
    config = carregar_config(ARQUIVO_PADRAO)
    assert config.provedores[0].nome == "openrouter"
    assert config.max_tokens == 1024


def test_validador_sai_com_codigo_0_quando_ok():
    resultado = subprocess.run([sys.executable, "scripts/validar_config.py"], cwd=RAIZ, capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stdout
    assert "✅" in resultado.stdout


def test_validador_sai_com_codigo_1_e_escreve_resumo(tmp_path, projeto):
    arquivo = projeto / "config.yaml"
    arquivo.write_text(yaml.safe_dump(com(aparencia__cor_principal="#12345G")), encoding="utf-8")
    resumo = tmp_path / "resumo.md"
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "scripts/validar_config.py"), str(arquivo)],
        capture_output=True,
        text=True,
        env={"GITHUB_STEP_SUMMARY": str(resumo), "PATH": ""},
    )
    assert resultado.returncode == 1
    assert "#12345G" in resultado.stdout
    assert "#12345G" in resumo.read_text(encoding="utf-8")


# ------------------------------------------------------------------ padrões


def test_valores_padrao_sao_aplicados(projeto):
    arquivo = projeto / "config.yaml"
    arquivo.write_text(yaml.safe_dump(CONFIG_BASE), encoding="utf-8")
    config = carregar_config(arquivo)
    assert config.cor_secundaria == "#0F2540"  # igual à principal
    assert config.logo_altura == 80
    assert config.max_tokens == 1024
    assert config.temperatura == 0.5
    assert config.tempo_limite_segundos == 30
    assert config.max_caracteres_pergunta == 2000
    assert config.max_mensagens_historico == 10
    assert config.exemplos == []


def test_zero_e_aceito_onde_permitido(projeto):
    dados = com(ia={**CONFIG_BASE["ia"], "temperatura": 0, "max_mensagens_historico": 0})
    arquivo = projeto / "config.yaml"
    arquivo.write_text(yaml.safe_dump(dados), encoding="utf-8")
    config = carregar_config(arquivo)
    assert config.temperatura == 0.0
    assert config.max_mensagens_historico == 0


# ---------------------------------------------------------- T1: YAML válido


def test_t1_arquivo_inexistente(tmp_path):
    with pytest.raises(ErroConfig, match="não foi encontrado"):
        carregar_config(tmp_path / "config.yaml")


def test_t1_yaml_quebrado_mostra_linha(tmp_path):
    arquivo = tmp_path / "config.yaml"
    arquivo.write_text('assistente:\n  nome: "sem fechar aspas\n  descricao: x\n', encoding="utf-8")
    with pytest.raises(ErroConfig, match=r"YAML inválido na linha \d+"):
        carregar_config(arquivo)


def test_t1_tab_tem_dica_especifica(tmp_path):
    arquivo = tmp_path / "config.yaml"
    arquivo.write_text("assistente:\n\tnome: x\n", encoding="utf-8")
    with pytest.raises(ErroConfig, match="TAB"):
        carregar_config(arquivo)


@pytest.mark.parametrize("dados", [None, "texto solto", [1, 2]])
def test_t1_conteudo_sem_campos(dados, projeto):
    assert validar(dados, projeto)


# ------------------------------------------------- T2: obrigatórios presentes


@pytest.mark.parametrize("secao", ["assistente", "aparencia", "ia", "comportamento"])
def test_t2_secao_obrigatoria_ausente(secao, projeto):
    dados = copy.deepcopy(CONFIG_BASE)
    del dados[secao]
    assert f"`{secao}`: seção obrigatória ausente" in erros_de(dados, projeto)


@pytest.mark.parametrize(
    "secao,campo",
    [("assistente", "nome"), ("assistente", "descricao"), ("comportamento", "instrucoes")],
)
@pytest.mark.parametrize("valor", [None, "", "   "])
def test_t2_texto_obrigatorio_vazio(secao, campo, valor, projeto):
    erros = erros_de(com(**{f"{secao}__{campo}": valor}), projeto)
    assert f"`{secao}.{campo}`: campo obrigatório vazio" in erros


def test_t2_provedores_vazio(projeto):
    assert "informe pelo menos 1 provedor" in erros_de(com(ia={"provedores": []}), projeto)


def test_t2_varios_erros_de_uma_vez(projeto):
    dados = com(assistente__nome="", aparencia__cor_principal="azul")
    assert len(validar(dados, projeto)) == 2


# ----------------------------------------------------- T3: tipos e faixas


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("max_tokens", "mil"),
        ("max_tokens", 10),
        ("max_tokens", 99999),
        ("max_tokens", 1.5),
        ("max_tokens", True),
        ("temperatura", 3),
        ("temperatura", -0.1),
        ("temperatura", "0,5"),
        ("tempo_limite_segundos", 1),
        ("max_caracteres_pergunta", 50),
        ("max_mensagens_historico", 51),
    ],
)
def test_t3_numeros_invalidos(campo, valor, projeto):
    dados = com(ia={**CONFIG_BASE["ia"], campo: valor})
    assert f"`ia.{campo}`" in erros_de(dados, projeto)


@pytest.mark.parametrize("altura", [10, 500, "80px"])
def test_t3_altura_logo_invalida(altura, projeto):
    assert "`aparencia.logo_altura`" in erros_de(com(aparencia__logo_altura=altura), projeto)


def test_t3_nome_longo_demais(projeto):
    assert "tem 61 caracteres" in erros_de(com(assistente__nome="x" * 61), projeto)


def test_t3_instrucoes_curtas_demais(projeto):
    assert "`comportamento.instrucoes`: tem 5 caracteres" in erros_de(com(comportamento__instrucoes="curto"), projeto)


def test_t3_nome_numerico(projeto):
    assert "deve ser um texto" in erros_de(com(assistente__nome=123), projeto)


def test_t3_exemplos(projeto):
    assert "máximo é 6" in erros_de(com(exemplos=["a"] * 7), projeto)
    assert "máximo é 150" in erros_de(com(exemplos=["x" * 151]), projeto)
    assert "pergunta vazia" in erros_de(com(exemplos=["ok", ""]), projeto)
    assert "deve ser uma lista" in erros_de(com(exemplos="uma pergunta"), projeto)


# ------------------------------------------------------------- T4: cores


@pytest.mark.parametrize("cor", ["#0F2540", "#fff", "#AbCdEf"])
def test_t4_cores_validas(cor, projeto):
    assert validar(com(aparencia__cor_principal=cor, aparencia__cor_secundaria=cor), projeto) == []


@pytest.mark.parametrize("cor", ["#12345G", "0F2540", "azul-claro", "#12345", "#1234567", 123])
def test_t4_cores_invalidas(cor, projeto):
    assert "não é uma cor válida" in erros_de(com(aparencia__cor_principal=cor), projeto)


def test_t4_cor_sem_aspas_vira_comentario(projeto):
    texto = yaml.safe_dump(CONFIG_BASE).replace("cor_principal: '#0F2540'", "cor_principal: #0F2540")
    dados = yaml.safe_load(texto)
    assert "ENTRE ASPAS" in erros_de(dados, projeto)


def test_t4_cor_secundaria_vazia_mas_declarada(projeto):
    assert "ENTRE ASPAS" in erros_de(com(aparencia__cor_secundaria=None), projeto)


# -------------------------------------------------------------- T5: logo


def test_t5_logo_inexistente(projeto):
    assert "não encontrado" in erros_de(com(aparencia__logo="assets/minha-logo.png"), projeto)


def test_t5_logo_com_maiusculas_diferentes(projeto):
    erros = erros_de(com(aparencia__logo="assets/Logo.png"), projeto)
    assert "não encontrado" in erros
    assert "assets/logo.png" in erros  # sugere o nome certo


def test_t5_logo_fora_de_assets(projeto):
    assert "dentro da pasta 'assets/'" in erros_de(com(aparencia__logo="logo.png"), projeto)
    assert "dentro da pasta 'assets/'" in erros_de(com(aparencia__logo="assets/../config.yaml"), projeto)


def test_t5_logo_extensao_invalida(projeto):
    (projeto / "assets" / "logo.gif").write_bytes(b"GIF")
    assert "extensão '.gif' não aceita" in erros_de(com(aparencia__logo="assets/logo.gif"), projeto)


def test_t5_logo_grande_demais(projeto):
    (projeto / "assets" / "grande.png").write_bytes(b"0" * (1024 * 1024 + 1))
    assert "o máximo é 1 MB" in erros_de(com(aparencia__logo="assets/grande.png"), projeto)


def test_t5_logo_ausente(projeto):
    assert "`aparencia.logo`: campo obrigatório" in erros_de(com(aparencia__logo=""), projeto)


# --------------------------------------------------------- T6: provedores


def test_t6_tres_provedores_validos(projeto):
    provedores = [
        {"nome": "openrouter", "modelo": "a"},
        {"nome": "anthropic", "modelo": "b"},
        {"nome": "openai", "modelo": "c"},
    ]
    assert validar(com(ia={"provedores": provedores}), projeto) == []


def test_t6_nome_invalido_com_sugestao(projeto):
    erros = erros_de(com(ia={"provedores": [{"nome": "open-ai", "modelo": "x"}]}), projeto)
    assert '"open-ai" não é aceito' in erros
    assert "Você quis dizer 'openai'?" in erros


def test_t6_nome_em_maiusculas(projeto):
    assert "não é aceito" in erros_de(com(ia={"provedores": [{"nome": "OpenAI", "modelo": "x"}]}), projeto)


def test_t6_provedor_repetido(projeto):
    provedores = [{"nome": "anthropic", "modelo": "a"}, {"nome": "anthropic", "modelo": "b"}]
    assert "aparece mais de uma vez" in erros_de(com(ia={"provedores": provedores}), projeto)


def test_t6_modelo_vazio(projeto):
    assert "`ia.provedores[1].modelo`: obrigatório" in erros_de(
        com(ia={"provedores": [{"nome": "openai", "modelo": ""}]}), projeto
    )


def test_t6_mais_de_tres(projeto):
    provedores = [{"nome": n, "modelo": "x"} for n in ("openrouter", "anthropic", "openai", "openai")]
    assert "o máximo é 3" in erros_de(com(ia={"provedores": provedores}), projeto)


def test_t6_item_sem_formato(projeto):
    assert "precisa de 'nome' e 'modelo'" in erros_de(com(ia={"provedores": ["openai"]}), projeto)


# ---------------------------------------------------- T7: campos desconhecidos


def test_t7_erro_de_digitacao_com_sugestao(projeto):
    dados = com(aparencia={**CONFIG_BASE["aparencia"], "cor_principall": "#000000"})
    erros = erros_de(dados, projeto)
    assert "`aparencia.cor_principall`: campo desconhecido" in erros
    assert "Você quis dizer `aparencia.cor_principal`?" in erros


def test_t7_secao_desconhecida(projeto):
    dados = {**CONFIG_BASE, "aparência": {}}
    assert "`aparência`: campo desconhecido" in erros_de(dados, projeto)


def test_t7_campo_desconhecido_em_provedor(projeto):
    dados = com(ia={"provedores": [{"nome": "openai", "modelo": "x", "modleo": "y"}]})
    assert "Você quis dizer `modelo`?" in erros_de(dados, projeto)


def test_t7_chave_de_api_no_config_e_recusada(projeto):
    # A chave falsa é montada em partes para o próprio teste não disparar o T8.
    chave_falsa = "sk-" + "ant-" + "api03-" + "a" * 30
    dados = com(assistente__descricao=f"minha chave {chave_falsa}")
    assert "parece conter uma chave de API" in erros_de(dados, projeto)
