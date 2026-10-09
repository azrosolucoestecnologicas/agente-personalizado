"""Limite de uso por visitante (spec da Parte 3, RF60).

Conta as perguntas por IP em duas janelas:
- por minuto: janela deslizante de 60 segundos;
- por dia: até a meia-noite UTC.

Os contadores ficam na memória do servidor (um contêiner só). Se o serviço
reiniciar, eles zeram, o que é aceitável para proteger a cota de IA.
Todo limite vale aqui, no servidor: desabilitar o botão na tela não protege nada.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

JANELA_MINUTO = 60.0
MAX_VISITANTES = 10_000  # acima disso, limpa quem não pergunta há mais de um minuto


class LimiteDeUso:
    def __init__(self, por_minuto: int, por_dia: int, relogio: Callable[[], float] = time.time):
        self.por_minuto = por_minuto
        self.por_dia = por_dia
        self._relogio = relogio
        self._trava = threading.Lock()
        self._minuto: dict[str, deque[float]] = {}
        self._dia: dict[str, tuple[str, int]] = {}  # ip -> (data UTC, quantas perguntas)

    def tentar(self, ip: str) -> int | None:
        """Registra a pergunta e devolve None, ou devolve quantos segundos esperar (sem registrar)."""
        agora = self._relogio()
        hoje = datetime.fromtimestamp(agora, UTC).date().isoformat()
        with self._trava:
            if len(self._minuto) > MAX_VISITANTES:
                self._limpar(agora)
            recentes = self._minuto.setdefault(ip, deque())
            while recentes and agora - recentes[0] >= JANELA_MINUTO:
                recentes.popleft()
            data, no_dia = self._dia.get(ip, (hoje, 0))
            if data != hoje:
                no_dia = 0
            if no_dia >= self.por_dia:
                return _segundos_ate_meia_noite(agora)
            if len(recentes) >= self.por_minuto:
                return max(1, int(JANELA_MINUTO - (agora - recentes[0]) + 0.999))
            recentes.append(agora)
            self._dia[ip] = (hoje, no_dia + 1)
            return None

    def _limpar(self, agora: float) -> None:
        for ip in [ip for ip, fila in self._minuto.items() if not fila or agora - fila[-1] >= JANELA_MINUTO]:
            del self._minuto[ip]


def _segundos_ate_meia_noite(agora: float) -> int:
    momento = datetime.fromtimestamp(agora, UTC)
    meia_noite = datetime.combine(momento.date() + timedelta(days=1), datetime.min.time(), UTC)
    return max(1, int((meia_noite - momento).total_seconds() + 0.999))


def ip_do_visitante(cabecalhos: Mapping[str, str], ip_da_conexao: str | None) -> str:
    """O Railway fica na frente do servidor: o IP real é o primeiro de X-Forwarded-For."""
    encaminhado = cabecalhos.get("x-forwarded-for", "")
    primeiro = encaminhado.split(",")[0].strip()
    return primeiro or ip_da_conexao or "desconhecido"


def mascarar_ip(ip: str) -> str:
    """Para o log: '200.150.10.20' vira '200.150.x.x' (não guarda o IP inteiro de ninguém)."""
    if "." in ip:
        partes = ip.split(".")
        return ".".join(partes[:2] + ["x"] * (len(partes) - 2))
    if ":" in ip:
        return ":".join(ip.split(":")[:2]) + ":…"
    return "x"
