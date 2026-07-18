"""Cliente da Betfair Exchange API (API-NG).

A Betfair é uma das poucas casas com API oficial para apostar programaticamente.
Requisitos na conta Betfair:
  1. Criar uma Application Key: https://developer.betfair.com
  2. Login interativo (usuário/senha) ou login por certificado (recomendado p/ bots)

Por segurança, TODA chamada de placeOrders passa por `dry_run` (padrão True):
nada é enviado de verdade até você passar dry_run=False explicitamente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import requests

IDENTITY_URL = "https://identitysso.betfair.com/api/login"
IDENTITY_CERT_URL = "https://identitysso-cert.betfair.com/api/certlogin"
BETTING_URL = "https://api.betfair.com/exchange/betting/rest/v1.0"


class BetfairError(RuntimeError):
    pass


@dataclass
class OrdemAposta:
    market_id: str
    selection_id: int
    lado: str          # "BACK" (a favor) ou "LAY" (contra)
    odd: float
    stake: float


class BetfairClient:
    def __init__(
        self,
        app_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
    ):
        self.app_key = app_key or os.environ.get("BETFAIR_APP_KEY", "")
        self.username = username or os.environ.get("BETFAIR_USERNAME", "")
        self.password = password or os.environ.get("BETFAIR_PASSWORD", "")
        self.cert_file = cert_file or os.environ.get("BETFAIR_CERT_FILE")
        self.key_file = key_file or os.environ.get("BETFAIR_KEY_FILE")
        self.session_token: Optional[str] = None
        if not self.app_key:
            raise BetfairError("BETFAIR_APP_KEY não configurada (veja .env.example)")

    # ------------------------------------------------------------------
    # Autenticação
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Faz login. Usa certificado se configurado (recomendado), senão interativo."""
        headers = {
            "X-Application": self.app_key,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"username": self.username, "password": self.password}

        if self.cert_file and self.key_file:
            resp = requests.post(
                IDENTITY_CERT_URL, data=data, headers=headers,
                cert=(self.cert_file, self.key_file), timeout=30,
            )
            payload = resp.json()
            if payload.get("loginStatus") != "SUCCESS":
                raise BetfairError(f"Login por certificado falhou: {payload}")
            self.session_token = payload["sessionToken"]
        else:
            resp = requests.post(IDENTITY_URL, data=data, headers=headers, timeout=30)
            payload = resp.json()
            if payload.get("status") != "SUCCESS":
                raise BetfairError(f"Login falhou: {payload}")
            self.session_token = payload["token"]

    def _headers(self) -> dict[str, str]:
        if not self.session_token:
            raise BetfairError("Não autenticado — chame login() primeiro")
        return {
            "X-Application": self.app_key,
            "X-Authentication": self.session_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, metodo: str, body: dict[str, Any]) -> Any:
        resp = requests.post(
            f"{BETTING_URL}/{metodo}/", json=body, headers=self._headers(), timeout=30
        )
        if resp.status_code != 200:
            raise BetfairError(f"{metodo} retornou {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    # ------------------------------------------------------------------
    # Consulta de mercados
    # ------------------------------------------------------------------

    def buscar_mercados_futebol(self, texto: str, max_resultados: int = 10) -> list[dict]:
        """Busca mercados MATCH_ODDS de futebol cujo evento contenha o texto."""
        return self._post(
            "listMarketCatalogue",
            {
                "filter": {
                    "eventTypeIds": ["1"],  # 1 = futebol
                    "textQuery": texto,
                    "marketTypeCodes": ["MATCH_ODDS"],
                },
                "maxResults": max_resultados,
                "marketProjection": ["EVENT", "RUNNER_DESCRIPTION", "MARKET_START_TIME"],
            },
        )

    def odds_do_mercado(self, market_id: str) -> dict:
        """Retorna o book (melhores odds disponíveis) de um mercado."""
        books = self._post(
            "listMarketBook",
            {
                "marketIds": [market_id],
                "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
            },
        )
        if not books:
            raise BetfairError(f"Mercado {market_id} não encontrado")
        return books[0]

    # ------------------------------------------------------------------
    # Execução de apostas
    # ------------------------------------------------------------------

    def apostar(self, ordem: OrdemAposta, dry_run: bool = True) -> dict:
        """Envia uma aposta LIMIT para a exchange.

        Com dry_run=True (padrão) apenas simula e retorna o payload que seria
        enviado, sem tocar na conta.
        """
        body = {
            "marketId": ordem.market_id,
            "instructions": [
                {
                    "selectionId": ordem.selection_id,
                    "side": ordem.lado,
                    "orderType": "LIMIT",
                    "limitOrder": {
                        "size": round(ordem.stake, 2),
                        "price": ordem.odd,
                        "persistenceType": "LAPSE",
                    },
                }
            ],
        }
        if dry_run:
            return {"dry_run": True, "payload": body}

        resultado = self._post("placeOrders", body)
        if resultado.get("status") != "SUCCESS":
            raise BetfairError(f"placeOrders falhou: {resultado}")
        return resultado

    def saldo_conta(self) -> dict:
        """Consulta fundos disponíveis na conta (Accounts API)."""
        resp = requests.post(
            "https://api.betfair.com/exchange/account/rest/v1.0/getAccountFunds/",
            json={}, headers=self._headers(), timeout=30,
        )
        if resp.status_code != 200:
            raise BetfairError(f"getAccountFunds retornou {resp.status_code}: {resp.text[:300]}")
        return resp.json()
