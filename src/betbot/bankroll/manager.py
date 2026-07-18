"""Gestão de banca: staking por Kelly fracionado, limites e histórico em SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ..models import ValueBet


@dataclass
class ConfigBanca:
    kelly_fracao: float = 0.25        # fração do Kelly (0.25 = quarter Kelly, conservador)
    stake_max_pct: float = 0.05       # nunca apostar mais de 5% da banca em uma aposta
    stake_min: float = 2.0            # stake mínima aceita pela maioria das casas
    stop_loss_diario_pct: float = 0.10   # para de apostar ao perder 10% da banca no dia
    stop_win_diario_pct: float = 0.20    # para de apostar ao ganhar 20% da banca no dia
    exposicao_max_pct: float = 0.15   # soma das stakes abertas limitada a 15% da banca


def kelly(prob: float, odd: float) -> float:
    """Fração de Kelly pura: f = (p*b - q) / b, onde b = odd - 1."""
    b = odd - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - prob
    f = (prob * b - q) / b
    return max(f, 0.0)


class GestorBanca:
    def __init__(self, db_path: str | Path = "banca.db", config: ConfigBanca | None = None):
        self.config = config or ConfigBanca()
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._criar_tabelas()

    def _criar_tabelas(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS movimentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                tipo TEXT NOT NULL,          -- deposito | saque | aposta | retorno
                valor REAL NOT NULL,          -- negativo para saídas
                descricao TEXT
            );
            CREATE TABLE IF NOT EXISTS apostas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                jogo_id TEXT NOT NULL,
                descricao TEXT NOT NULL,
                mercado TEXT NOT NULL,
                selecao TEXT NOT NULL,
                odd REAL NOT NULL,
                probabilidade REAL NOT NULL,
                ev REAL NOT NULL,
                stake REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'aberta',  -- aberta | ganha | perdida | anulada
                retorno REAL
            );
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Saldo e movimentos
    # ------------------------------------------------------------------

    def saldo(self) -> float:
        row = self.conn.execute("SELECT COALESCE(SUM(valor), 0) AS s FROM movimentos").fetchone()
        return float(row["s"])

    def depositar(self, valor: float, descricao: str = "depósito") -> None:
        self._movimento("deposito", abs(valor), descricao)

    def sacar(self, valor: float, descricao: str = "saque") -> None:
        if abs(valor) > self.saldo():
            raise ValueError("Saque maior que o saldo disponível")
        self._movimento("saque", -abs(valor), descricao)

    def _movimento(self, tipo: str, valor: float, descricao: str) -> None:
        self.conn.execute(
            "INSERT INTO movimentos (data, tipo, valor, descricao) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), tipo, valor, descricao),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Limites diários
    # ------------------------------------------------------------------

    def resultado_do_dia(self) -> float:
        """Lucro/prejuízo realizado hoje (apostas liquidadas + stakes de hoje)."""
        hoje = date.today().isoformat()
        row = self.conn.execute(
            """SELECT COALESCE(SUM(valor), 0) AS s FROM movimentos
               WHERE tipo IN ('aposta', 'retorno') AND data LIKE ?""",
            (f"{hoje}%",),
        ).fetchone()
        return float(row["s"])

    def exposicao_aberta(self) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(stake), 0) AS s FROM apostas WHERE status = 'aberta'"
        ).fetchone()
        return float(row["s"])

    def pode_apostar(self) -> tuple[bool, str]:
        banca = self.saldo()
        if banca <= 0:
            return False, "Banca zerada — faça um depósito antes de apostar."
        resultado = self.resultado_do_dia()
        if resultado <= -banca * self.config.stop_loss_diario_pct:
            return False, f"Stop-loss diário atingido ({resultado:.2f}). Volte amanhã."
        if resultado >= banca * self.config.stop_win_diario_pct:
            return False, f"Stop-win diário atingido (+{resultado:.2f}). Proteja o lucro."
        if self.exposicao_aberta() >= banca * self.config.exposicao_max_pct:
            return False, "Exposição máxima em apostas abertas atingida."
        return True, "ok"

    # ------------------------------------------------------------------
    # Staking
    # ------------------------------------------------------------------

    def calcular_stake(self, bet: ValueBet) -> float:
        """Stake por Kelly fracionado, limitada pelo teto por aposta."""
        banca = self.saldo()
        f = kelly(bet.probabilidade, bet.odd) * self.config.kelly_fracao
        stake = banca * f
        stake = min(stake, banca * self.config.stake_max_pct)
        if stake < self.config.stake_min:
            return 0.0
        return round(stake, 2)

    def registrar_aposta(self, bet: ValueBet) -> int:
        """Registra a aposta e debita a stake da banca. Retorna o id."""
        cur = self.conn.execute(
            """INSERT INTO apostas
               (data, jogo_id, descricao, mercado, selecao, odd, probabilidade, ev, stake)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                bet.jogo_id, bet.descricao, bet.mercado.value, bet.selecao,
                bet.odd, bet.probabilidade, bet.ev, bet.stake,
            ),
        )
        self._movimento("aposta", -bet.stake, bet.descricao)
        self.conn.commit()
        return int(cur.lastrowid)

    def liquidar_aposta(self, aposta_id: int, resultado: str) -> None:
        """Liquida uma aposta: resultado em {'ganha', 'perdida', 'anulada'}."""
        row = self.conn.execute("SELECT * FROM apostas WHERE id = ?", (aposta_id,)).fetchone()
        if row is None:
            raise ValueError(f"Aposta {aposta_id} não encontrada")
        if row["status"] != "aberta":
            raise ValueError(f"Aposta {aposta_id} já liquidada ({row['status']})")

        if resultado == "ganha":
            retorno = row["stake"] * row["odd"]
        elif resultado == "anulada":
            retorno = row["stake"]
        elif resultado == "perdida":
            retorno = 0.0
        else:
            raise ValueError("resultado deve ser 'ganha', 'perdida' ou 'anulada'")

        self.conn.execute(
            "UPDATE apostas SET status = ?, retorno = ? WHERE id = ?",
            (resultado, retorno, aposta_id),
        )
        if retorno > 0:
            self._movimento("retorno", retorno, f"retorno aposta #{aposta_id} ({resultado})")
        self.conn.commit()

    # ------------------------------------------------------------------
    # Relatórios
    # ------------------------------------------------------------------

    def historico_apostas(self, limite: int = 50) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM apostas ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
        )

    def estatisticas(self) -> dict:
        row = self.conn.execute(
            """SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN status = 'ganha' THEN 1 ELSE 0 END) AS ganhas,
                 SUM(CASE WHEN status = 'perdida' THEN 1 ELSE 0 END) AS perdidas,
                 SUM(CASE WHEN status = 'aberta' THEN 1 ELSE 0 END) AS abertas,
                 COALESCE(SUM(CASE WHEN status != 'aberta'
                                   THEN COALESCE(retorno, 0) - stake ELSE 0 END), 0) AS lucro
               FROM apostas"""
        ).fetchone()
        liquidadas = (row["ganhas"] or 0) + (row["perdidas"] or 0)
        return {
            "saldo": self.saldo(),
            "total_apostas": row["total"],
            "ganhas": row["ganhas"] or 0,
            "perdidas": row["perdidas"] or 0,
            "abertas": row["abertas"] or 0,
            "taxa_acerto": (row["ganhas"] or 0) / liquidadas if liquidadas else 0.0,
            "lucro_liquidado": float(row["lucro"]),
        }
