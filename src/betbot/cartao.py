"""Geração e formatação do cartão de apostas."""

from __future__ import annotations

import json
from pathlib import Path

from .bankroll.manager import GestorBanca
from .models import Cartao, ValueBet


def montar_cartao(value_bets: list[ValueBet], gestor: GestorBanca) -> Cartao:
    """Monta o cartão aplicando gestão de banca a cada value bet.

    Respeita stop-loss/stop-win e exposição; stakes por Kelly fracionado.
    Apostas cuja stake calculada fica abaixo do mínimo são descartadas.
    """
    cartao = Cartao(banca_atual=gestor.saldo())

    ok, motivo = gestor.pode_apostar()
    if not ok:
        cartao.observacoes.append(f"BLOQUEADO: {motivo}")
        return cartao

    exposicao_limite = gestor.saldo() * gestor.config.exposicao_max_pct
    exposicao = gestor.exposicao_aberta()

    for bet in value_bets:
        stake = gestor.calcular_stake(bet)
        if stake <= 0:
            cartao.observacoes.append(
                f"Descartada (stake abaixo do mínimo): {bet.descricao}"
            )
            continue
        if exposicao + stake > exposicao_limite:
            cartao.observacoes.append(
                f"Descartada (exposição máxima): {bet.descricao}"
            )
            continue
        bet.stake = stake
        exposicao += stake
        cartao.apostas.append(bet)

    cartao.stake_total = round(sum(b.stake for b in cartao.apostas), 2)
    return cartao


def salvar_cartao(cartao: Cartao, caminho: str | Path) -> None:
    Path(caminho).write_text(
        json.dumps(cartao.model_dump(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def carregar_cartao(caminho: str | Path) -> Cartao:
    return Cartao.model_validate_json(Path(caminho).read_text(encoding="utf-8"))


def formatar_cartao(cartao: Cartao) -> str:
    linhas = [
        "=" * 62,
        "  CARTÃO DE APOSTAS",
        f"  Gerado em: {cartao.criado_em}   Banca: R$ {cartao.banca_atual:.2f}",
        "=" * 62,
    ]
    if not cartao.apostas:
        linhas.append("  Nenhuma aposta com valor encontrada hoje. Não forçar é lucro.")
    for i, b in enumerate(cartao.apostas, 1):
        linhas += [
            f"  {i}. {b.descricao}",
            f"     Odd: {b.odd:.2f} | Prob. estimada: {b.probabilidade:.1%} | "
            f"EV: {b.ev:+.1%} | Confiança: {b.confianca:.0%}",
            f"     Stake sugerida: R$ {b.stake:.2f}",
            "",
        ]
    if cartao.apostas:
        linhas.append(f"  Stake total do cartão: R$ {cartao.stake_total:.2f}")
    for obs in cartao.observacoes:
        linhas.append(f"  [!] {obs}")
    linhas.append("=" * 62)
    return "\n".join(linhas)
