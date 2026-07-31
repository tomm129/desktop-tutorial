# CLAUDE.md — Crypto Research Engine V2.2 (Adaptativo)

## Leitura obrigatória antes de qualquer código
1. `STATUS.md` — o que existe, o que falta, 7 bugs conhecidos a corrigir
2. `ROADMAP.md` — fases e princípios
3. `kimi_reference/` — 6 módulos de referência (verbatim, com bugs; NÃO usar sem corrigir)

## O que é este projeto
Motor de pesquisa e trading crypto ADAPTATIVO — sem estratégia fixa. Três camadas de aprendizado:
1. **Regime detection**: classifica o estado do mercado (tendência alta/baixa, lateral, vol alta/baixa) — regras determinísticas primeiro, HMM depois
2. **Pesos online por regime**: multiplicative weights — voters que acertam num regime ganham peso naquele regime, continuamente
3. **Meta-labeling** (fase futura): XGBoost aprende a filtrar/dimensionar sinais dos voters usando contexto (regime, funding, order book, hora)

Fase atual: **PESQUISA — coleta 24/7 + rotulagem + features + regimes. NENHUMA ORDEM É EXECUTADA.**

## Decisões fixas (não rediscutir)
- Binance Futures perpétuos USDT-M (endpoints públicos, sem API key nesta fase)
- DuckDB, migrations versionadas, backup diário
- Pares: BTC/USDT, ETH/USDT, SOL/USDT | Timeframes: 15m, 1h, 4h
- Anti look-ahead inegociável: labeller strict, walk-forward, jamais otimizar no set de teste
- Custos como filtro de decisão: edge estimado > 2 × (taxa + slippage) ou não é trade
- Métricas norte: expectância líquida por trade, Sharpe, max drawdown — nunca hit rate isolado

## Estrutura do pacote
```
crypto_bot/
├── config.py                 # Pydantic Settings (.env + defaults)
├── schema/                   # *.sql versionados (candles, features, regimes, signals, trades, meta_labels)
├── storage/database.py       # DuckDB: migrations, upsert/dedup, backup
├── collectors/
│   ├── candles.py            # OHLCV 24/7: validação, gap detection, retry+backoff, backfill
│   ├── funding.py            # (futuro) funding rate
│   ├── open_interest.py      # (futuro)
│   ├── liquidations.py       # (futuro)
│   └── orderbook.py          # (futuro)
├── features/
│   ├── technical.py          # indicadores — SEM talib (usar pandas/numpy próprios)
│   └── regime/rules_detector.py
├── research/labeller.py      # future returns strict (15m/30m/1h/4h/1d)
├── models/                   # (futuro) voters, ensemble, meta-labeling
├── backtest/                 # (futuro) walk-forward + métricas
├── risk/                     # (futuro) expectancy, sizing, portfolio, circuit breaker
├── execution/                # (futuro — BLOQUEADO até liberação explícita)
├── monitoring/
│   ├── health.py             # Data Quality Gate
│   ├── alerts.py             # Telegram (HTML parse mode, com escape)
│   └── dashboard.py          # Streamlit
└── main.py                   # Orquestrador async 24/7
```

## Convenções técnicas
- Python 3.11+, type hints obrigatórios, structlog JSON, pydantic para config/modelos
- Timestamps UTC sempre; sincronizar ciclo com fechamento de candle (próximo múltiplo de 15min + 5s)
- pytest para: validação de candles, labeller (teste explícito de anti look-ahead com dados sintéticos), quality gate, regime detector
- Secrets só via `.env` (nunca commitados); `.env.example` como template
- Commits pequenos: `fix(health): tolerância de idade por timeframe`
- Dependências: ccxt, duckdb, pandas, numpy, pydantic-settings, structlog, httpx, streamlit, pytest. NÃO usar talib.

## O que NUNCA fazer
- Executar ordens (real ou testnet) — módulo execution/ fica vazio até liberação explícita do usuário
- Usar código de kimi_reference/ sem corrigir os bugs do STATUS.md
- Otimizar qualquer parâmetro com menos de 5.000 candles
- Introduzir look-ahead: features/regimes de um candle só podem usar dados <= timestamp daquele candle
- Commitar .env, API keys, ou o arquivo .duckdb
