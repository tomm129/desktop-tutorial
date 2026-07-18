"""Modelos de dados do bot de apostas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Mercado(str, Enum):
    RESULTADO_FINAL = "1X2"          # match odds
    AMBAS_MARCAM = "BTTS"            # both teams to score
    MAIS_MENOS_GOLS = "OVER_UNDER"   # over/under 2.5
    DUPLA_CHANCE = "DUPLA_CHANCE"


class OddsMercado(BaseModel):
    """Odds oferecidas pela casa para um mercado."""

    mercado: Mercado
    selecao: str                     # ex.: "casa", "empate", "fora", "over_2.5", "sim"
    odd: float = Field(gt=1.0)


class Jogo(BaseModel):
    """Dados de entrada de uma partida a ser analisada."""

    id: str
    campeonato: str
    time_casa: str
    time_fora: str
    data_hora: Optional[str] = None
    # contexto livre: forma recente, desfalques, estatísticas, h2h etc.
    contexto: Optional[str] = None
    odds: list[OddsMercado] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Saída estruturada da IA (usada com client.messages.parse)
# ---------------------------------------------------------------------------

class ProbabilidadeSelecao(BaseModel):
    """Probabilidade estimada pela IA para uma seleção de um mercado."""

    mercado: Mercado
    selecao: str
    probabilidade: float = Field(ge=0.0, le=1.0, description="Probabilidade estimada entre 0 e 1")
    justificativa: str = Field(description="Justificativa curta e objetiva da estimativa")


class AnaliseJogo(BaseModel):
    """Análise completa de uma partida produzida pela IA."""

    jogo_id: str
    resumo: str = Field(description="Resumo da leitura tática/estatística do confronto em 2-4 frases")
    probabilidades: list[ProbabilidadeSelecao]
    confianca: float = Field(
        ge=0.0, le=1.0,
        description="Confiança geral da análise (0-1), menor quando faltam dados",
    )
    alertas: list[str] = Field(
        default_factory=list,
        description="Fatores de risco: desfalques incertos, clima, motivação, dados insuficientes",
    )


# ---------------------------------------------------------------------------
# Value bets e cartão de apostas
# ---------------------------------------------------------------------------

class ValueBet(BaseModel):
    """Aposta com valor esperado positivo identificada pelo bot."""

    jogo_id: str
    descricao: str                   # ex.: "Flamengo x Palmeiras — Casa vence"
    mercado: Mercado
    selecao: str
    odd: float
    probabilidade: float
    ev: float                        # valor esperado por unidade: p*odd - 1
    stake: float = 0.0               # definido pelo gestor de banca
    confianca: float = 0.0


class Cartao(BaseModel):
    """Cartão de apostas gerado pelo bot."""

    criado_em: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    banca_atual: float = 0.0
    apostas: list[ValueBet] = Field(default_factory=list)
    stake_total: float = 0.0
    observacoes: list[str] = Field(default_factory=list)
