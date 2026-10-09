"""Limite de uso por visitante (RF60), com relógio simulado."""

from __future__ import annotations

from agente.limites import LimiteDeUso, ip_do_visitante, mascarar_ip

MEIO_DIA = 1_800_014_400.0  # 2027-01-15 12:00 UTC


class Relogio:
    def __init__(self, agora=MEIO_DIA):
        self.agora = agora

    def __call__(self):
        return self.agora


def test_janela_deslizante_de_um_minuto():
    relogio = Relogio()
    limite = LimiteDeUso(por_minuto=3, por_dia=100, relogio=relogio)
    for segundo in (0, 10, 20):
        relogio.agora = MEIO_DIA + segundo
        assert limite.tentar("1.1.1.1") is None
    relogio.agora = MEIO_DIA + 30
    assert limite.tentar("1.1.1.1") == 30  # a 1ª pergunta sai da janela em 30 s
    relogio.agora = MEIO_DIA + 60
    assert limite.tentar("1.1.1.1") is None


def test_pedido_recusado_nao_conta():
    relogio = Relogio()
    limite = LimiteDeUso(por_minuto=1, por_dia=100, relogio=relogio)
    assert limite.tentar("ip") is None
    for _ in range(5):
        assert limite.tentar("ip") is not None
    relogio.agora += 60
    assert limite.tentar("ip") is None


def test_limite_do_dia_zera_a_meia_noite_utc():
    relogio = Relogio()
    limite = LimiteDeUso(por_minuto=100, por_dia=2, relogio=relogio)
    assert limite.tentar("ip") is None and limite.tentar("ip") is None
    assert limite.tentar("ip") == 12 * 3600
    relogio.agora = MEIO_DIA + 12 * 3600  # meia-noite
    assert limite.tentar("ip") is None


def test_visitantes_independentes():
    limite = LimiteDeUso(por_minuto=1, por_dia=10, relogio=Relogio())
    assert limite.tentar("a") is None and limite.tentar("b") is None
    assert limite.tentar("a") is not None


def test_ip_vem_do_x_forwarded_for():
    assert ip_do_visitante({"x-forwarded-for": "200.1.2.3, 10.0.0.1"}, "10.0.0.9") == "200.1.2.3"
    assert ip_do_visitante({}, "10.0.0.9") == "10.0.0.9"
    assert ip_do_visitante({}, None) == "desconhecido"


def test_mascarar_ip():
    assert mascarar_ip("200.150.10.20") == "200.150.x.x"
    assert mascarar_ip("2804:14c:1234::1") == "2804:14c:…"
