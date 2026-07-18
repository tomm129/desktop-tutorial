"""Busca de jogos, odds e resultados via The Odds API (the-odds-api.com).

Chave gratuita (500 requisições/mês): https://the-odds-api.com
Defina ODDS_API_KEY no .env.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

from ..models import Jogo, Mercado, OddsMercado

BASE_URL = "https://api.the-odds-api.com/v4"

LIGAS = {
    "serie-a": "soccer_brazil_campeonato",
    "serie-b": "soccer_brazil_serie_b",
    "premier-league": "soccer_epl",
    "la-liga": "soccer_spain_la_liga",
    "libertadores": "soccer_conmebol_copa_libertadores",
}

NOMES_LIGAS = {
    "serie-a": "Brasileirão Série A",
    "serie-b": "Brasileirão Série B",
    "premier-league": "Premier League",
    "la-liga": "La Liga",
    "libertadores": "Copa Libertadores",
}


class OddsApiError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        raise OddsApiError(
            "ODDS_API_KEY não configurada. Crie uma chave grátis em https://the-odds-api.com "
            "e adicione ao .env"
        )
    return key


def _sport_key(liga: str) -> str:
    if liga not in LIGAS:
        raise OddsApiError(f"Liga '{liga}' não suportada. Opções: {', '.join(LIGAS)}")
    return LIGAS[liga]


def buscar_jogos(liga: str = "serie-b", horas: int = 24) -> list[Jogo]:
    """Busca os próximos jogos da liga (até `horas` à frente) com as melhores odds.

    Mapeia h2h -> 1X2 (casa/empate/fora) e totals 2.5 -> over/under.
    Usa a MELHOR odd entre as casas listadas (maximiza chance de value).
    """
    resp = requests.get(
        f"{BASE_URL}/sports/{_sport_key(liga)}/odds",
        params={
            "apiKey": _api_key(),
            "regions": "eu,uk",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise OddsApiError(f"The Odds API retornou {resp.status_code}: {resp.text[:300]}")

    agora = datetime.now(timezone.utc)
    limite = agora + timedelta(hours=horas)
    jogos: list[Jogo] = []

    for evento in resp.json():
        comeco = datetime.fromisoformat(evento["commence_time"].replace("Z", "+00:00"))
        if not (agora <= comeco <= limite):
            continue

        casa, fora = evento["home_team"], evento["away_team"]
        melhores: dict[tuple[Mercado, str], float] = {}

        for bookmaker in evento.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market["key"] == "h2h":
                    for outcome in market["outcomes"]:
                        if outcome["name"] == casa:
                            selecao = "casa"
                        elif outcome["name"] == fora:
                            selecao = "fora"
                        else:
                            selecao = "empate"
                        chave = (Mercado.RESULTADO_FINAL, selecao)
                        melhores[chave] = max(melhores.get(chave, 0.0), float(outcome["price"]))
                elif market["key"] == "totals":
                    for outcome in market["outcomes"]:
                        if float(outcome.get("point", -1)) != 2.5:
                            continue
                        selecao = "over_2.5" if outcome["name"] == "Over" else "under_2.5"
                        chave = (Mercado.MAIS_MENOS_GOLS, selecao)
                        melhores[chave] = max(melhores.get(chave, 0.0), float(outcome["price"]))

        if not melhores:
            continue

        jogos.append(
            Jogo(
                id=evento["id"],
                campeonato=NOMES_LIGAS.get(liga, liga),
                time_casa=casa,
                time_fora=fora,
                data_hora=comeco.astimezone().isoformat(timespec="minutes"),
                contexto=(
                    f"Jogo do {NOMES_LIGAS.get(liga, liga)}. Use seu conhecimento sobre os "
                    "times (elenco, campanha, mando de campo). Se não tiver informação "
                    "recente sobre a fase atual das equipes, reduza a confiança."
                ),
                odds=[
                    OddsMercado(mercado=m, selecao=s, odd=odd)
                    for (m, s), odd in melhores.items()
                ],
            )
        )
    return jogos


def buscar_resultados(liga: str = "serie-b", dias: int = 3) -> dict[str, dict]:
    """Resultados de jogos encerrados nos últimos `dias`.

    Retorna {event_id: {"casa": str, "fora": str, "casa_gols": int, "fora_gols": int}}.
    """
    resp = requests.get(
        f"{BASE_URL}/sports/{_sport_key(liga)}/scores",
        params={"apiKey": _api_key(), "daysFrom": dias},
        timeout=30,
    )
    if resp.status_code != 200:
        raise OddsApiError(f"The Odds API retornou {resp.status_code}: {resp.text[:300]}")

    resultados: dict[str, dict] = {}
    for evento in resp.json():
        if not evento.get("completed") or not evento.get("scores"):
            continue
        placar = {s["name"]: int(s["score"]) for s in evento["scores"]}
        casa, fora = evento["home_team"], evento["away_team"]
        if casa not in placar or fora not in placar:
            continue
        resultados[evento["id"]] = {
            "casa": casa,
            "fora": fora,
            "casa_gols": placar[casa],
            "fora_gols": placar[fora],
        }
    return resultados
