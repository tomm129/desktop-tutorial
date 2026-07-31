# 🤖 Crypto Research Engine V2.2

Motor de pesquisa crypto **adaptativo** — coleta 24/7, features técnicas, detecção de regime e rotulagem temporal estrita (anti look-ahead).

> **Fase atual: PESQUISA. Nenhuma ordem é executada** (nem testnet). O módulo `execution/` fica vazio até liberação explícita.

Leia antes de mexer no código: [`CLAUDE.md`](CLAUDE.md) (regras do projeto), [`STATUS.md`](STATUS.md) (histórico do handoff e bugs corrigidos), [`ROADMAP.md`](ROADMAP.md) (fases).

## O que já funciona

- **Coleta OHLCV** — Binance Futures USDT-M (endpoints públicos, sem API key) via CCXT: BTC, ETH e SOL perpétuos em 15m/1h/4h, com validação OHLC, detecção de gaps, retry com backoff exponencial e backfill de 50 dias no primeiro boot
- **Storage DuckDB** — migrations versionadas (`crypto_bot/schema/*.sql`), dedup/upsert por anti-join, backup diário automático
- **Features técnicas** — RSI, SMA/EMA, Bollinger, ATR, momentum, volatilidade, OBV, price action — implementação própria em pandas/numpy (**sem TA-Lib**)
- **Regime detection** — regras determinísticas (ADX proxy, ATR percentil, volume, momentum) sobre candles+features
- **Labeller temporal estrito** — future returns 15m/30m/1h/4h/1d usando SOMENTE dados futuros, com teste que injeta preço absurdo no futuro e prova que não vaza para o passado
- **Data Quality Gate** — frescor por timeframe, gaps, presença de features/regimes
- **Alertas Telegram** — HTML com escape (opcional, via `.env`)
- **Orquestrador 24/7** — ciclo coleta → features → regimes → labels → health, sincronizado com o fechamento dos candles

Os 7 bugs conhecidos do handoff (ver `STATUS.md`) foram corrigidos na integração; os módulos originais do Kimi permanecem intocados em `kimi_reference/` como referência.

## Setup (desktop/VPS)

Requisitos: Python 3.11+

```bash
git clone <este-repo>
cd <pasta>
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # ajuste se quiser Telegram etc.
```

### Rodar os testes

```bash
pytest
```

### Rodar o motor de coleta 24/7

```bash
python -m crypto_bot.main
# ou: cryptobot
```

No primeiro boot faz backfill de ~50 dias (alguns minutos). Depois, um ciclo a cada fechamento de candle de 15m. Logs em JSON (structlog) no stdout. Dados em `data/crypto_bot.duckdb`, backups diários em `data/backups/`.

### Dashboard (opcional)

```bash
pip install -e ".[dashboard]"
streamlit run crypto_bot/monitoring/dashboard.py
```

### Deploy como serviço (VPS/Linux)

```bash
sudo cp deploy/cryptobot.service /etc/systemd/system/   # ajuste os caminhos no arquivo
sudo systemctl daemon-reload
sudo systemctl enable --now cryptobot
journalctl -u cryptobot -f
```

## Estrutura

```
crypto_bot/
├── config.py                  # pydantic-settings (.env + defaults)
├── schema/                    # migrations SQL versionadas
├── storage/database.py        # DuckDB: migrations, upsert, backup
├── collectors/candles.py      # coleta 24/7 com validação e retry
├── features/
│   ├── technical.py           # indicadores (pandas/numpy, sem TA-Lib)
│   ├── pipeline.py            # candles → features → regimes (garante o contrato do detector)
│   └── regime/rules_detector.py
├── research/labeller.py       # future returns estritos (anti look-ahead)
├── monitoring/
│   ├── health.py              # Data Quality Gate
│   ├── alerts.py              # Telegram (HTML + escape)
│   └── dashboard.py           # Streamlit
├── execution/                 # VAZIO — bloqueado até liberação explícita
└── main.py                    # orquestrador async 24/7
```

## Próximos passos (ROADMAP)

1. Deixar a coleta rodando 24/7 por 2 semanas (Fase 0: zero gaps, 5.000+ candles/par)
2. Baseline dos voters clichês antes de qualquer otimização (Fase 2)
3. Voters com edge real: funding rate spread, order book imbalance (Fase 3)
4. Somente depois: testnet → produção (Fases 5-6)
