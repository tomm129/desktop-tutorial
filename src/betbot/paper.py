"""Modo teste (paper trading): registra previsões sem apostar e mede a acertividade.

Cada previsão registrada guarda a probabilidade estimada pela IA e a odd do momento.
Quando o jogo termina, `conferir()` liquida as previsões e o relatório mostra:
  - taxa de acerto do palpite principal (1X2 com maior probabilidade)
  - taxa de acerto e ROI simulado das value bets (stake fixa de 1 unidade)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import AnaliseJogo, Jogo, Mercado, ValueBet


def _liquidar_selecao(mercado: str, selecao: str, casa_gols: int, fora_gols: int) -> bool:
    """True se a seleção venceu dado o placar final."""
    total = casa_gols + fora_gols
    if mercado == Mercado.RESULTADO_FINAL.value:
        vencedor = "casa" if casa_gols > fora_gols else ("fora" if fora_gols > casa_gols else "empate")
        return selecao == vencedor
    if mercado == Mercado.MAIS_MENOS_GOLS.value:
        if selecao == "over_2.5":
            return total > 2.5
        if selecao == "under_2.5":
            return total < 2.5
    if mercado == Mercado.AMBAS_MARCAM.value:
        ambas = casa_gols > 0 and fora_gols > 0
        return (selecao == "sim") == ambas
    raise ValueError(f"não sei liquidar {mercado}/{selecao}")


class ModoTeste:
    def __init__(self, db_path: str | Path = "banca.db"):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS previsoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criada_em TEXT NOT NULL,
                jogo_id TEXT NOT NULL,
                evento TEXT NOT NULL,
                liga TEXT NOT NULL,
                comeco TEXT,
                tipo TEXT NOT NULL,           -- palpite (1X2 mais provável) | value (EV+)
                mercado TEXT NOT NULL,
                selecao TEXT NOT NULL,
                odd REAL NOT NULL,
                probabilidade REAL NOT NULL,
                ev REAL NOT NULL,
                resultado TEXT,               -- NULL | acertou | errou
                placar TEXT,
                liquidada_em TEXT,
                UNIQUE (jogo_id, tipo, mercado, selecao)
            );
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------

    def registrar(self, jogo: Jogo, analise: AnaliseJogo, value_bets: list[ValueBet]) -> int:
        """Registra o palpite principal (1X2) e as value bets do jogo. Retorna qtd nova."""
        odds = {(o.mercado, o.selecao): o.odd for o in jogo.odds}
        linhas: list[tuple] = []

        # palpite principal: seleção 1X2 com maior probabilidade estimada
        probs_1x2 = [p for p in analise.probabilidades if p.mercado == Mercado.RESULTADO_FINAL]
        if probs_1x2:
            melhor = max(probs_1x2, key=lambda p: p.probabilidade)
            odd = odds.get((melhor.mercado, melhor.selecao), 0.0)
            linhas.append(
                ("palpite", melhor.mercado.value, melhor.selecao, odd,
                 melhor.probabilidade, round(melhor.probabilidade * odd - 1, 4) if odd else 0.0)
            )

        for vb in value_bets:
            linhas.append(("value", vb.mercado.value, vb.selecao, vb.odd, vb.probabilidade, vb.ev))

        novas = 0
        for tipo, mercado, selecao, odd, prob, ev in linhas:
            cur = self.conn.execute(
                """INSERT OR IGNORE INTO previsoes
                   (criada_em, jogo_id, evento, liga, comeco, tipo, mercado, selecao,
                    odd, probabilidade, ev)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    jogo.id, f"{jogo.time_casa} x {jogo.time_fora}", jogo.campeonato,
                    jogo.data_hora, tipo, mercado, selecao, odd, prob, ev,
                ),
            )
            novas += cur.rowcount
        self.conn.commit()
        return novas

    # ------------------------------------------------------------------

    def conferir(self, resultados: dict[str, dict]) -> int:
        """Liquida previsões abertas cujos jogos já terminaram. Retorna qtd liquidada."""
        abertas = self.conn.execute(
            "SELECT * FROM previsoes WHERE resultado IS NULL"
        ).fetchall()
        liquidadas = 0
        for prev in abertas:
            res = resultados.get(prev["jogo_id"])
            if res is None:
                continue
            acertou = _liquidar_selecao(
                prev["mercado"], prev["selecao"], res["casa_gols"], res["fora_gols"]
            )
            self.conn.execute(
                """UPDATE previsoes SET resultado = ?, placar = ?, liquidada_em = ?
                   WHERE id = ?""",
                (
                    "acertou" if acertou else "errou",
                    f"{res['casa_gols']}x{res['fora_gols']}",
                    datetime.now().isoformat(timespec="seconds"),
                    prev["id"],
                ),
            )
            liquidadas += 1
        self.conn.commit()
        return liquidadas

    # ------------------------------------------------------------------

    def relatorio(self) -> dict:
        def stats(tipo: str) -> dict:
            rows = self.conn.execute(
                "SELECT * FROM previsoes WHERE tipo = ? AND resultado IS NOT NULL", (tipo,)
            ).fetchall()
            acertos = sum(1 for r in rows if r["resultado"] == "acertou")
            # ROI simulado com stake fixa de 1 unidade por previsão
            retorno = sum(r["odd"] if r["resultado"] == "acertou" else 0.0 for r in rows)
            investido = float(len(rows))
            return {
                "liquidadas": len(rows),
                "acertos": acertos,
                "taxa": acertos / len(rows) if rows else 0.0,
                "roi": (retorno - investido) / investido if investido else 0.0,
            }

        abertas = self.conn.execute(
            "SELECT COUNT(*) AS n FROM previsoes WHERE resultado IS NULL"
        ).fetchone()["n"]
        return {"palpite": stats("palpite"), "value": stats("value"), "abertas": abertas}

    def listar(self, limite: int = 40) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM previsoes ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
        )
