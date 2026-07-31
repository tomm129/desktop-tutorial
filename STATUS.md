# STATUS DO PROJETO — Handoff Kimi → Claude Code
Data: 30/07/2026

> **ATUALIZAÇÃO 31/07/2026 (Claude Code):** as etapas 1–4 do PROMPT_INICIAL.md foram
> concluídas: esqueleto do pacote recriado (config, schemas SQL versionados,
> storage DuckDB com migrations/upsert/backup), coletor com validação/retry/backfill,
> os 6 módulos de `kimi_reference/` integrados com os **7 bugs abaixo corrigidos**,
> e 29 testes pytest passando (incluindo anti look-ahead com dados sintéticos).
> Pipeline validado ponta a ponta com exchange simulada (quality gate 9/9 PASS).
> A coleta real contra a Binance deve ser executada no desktop/VPS (a rede do
> ambiente de desenvolvimento remoto bloqueia a API). Ver README.md para operação.
> Ajustes além dos 7 bugs: idade no health gate medida a partir do FECHAMENTO do
> candle (não da abertura) e backfill default de 50 dias (300 candles de 4h =
> 200 de warm-up das features + 50 do rolling do regime detector).

## Origem
A arquitetura V2.2 foi desenhada em conversa com o Kimi (Moonshot AI), que iniciou a implementação mas esgotou o budget de execução no meio. Resultado: ~12 arquivos criados no sandbox do Kimi (conteúdo NÃO disponível aqui) + 6 módulos colados no chat (disponíveis em `kimi_reference/`, verbatim, COM BUGS CONHECIDOS documentados abaixo).

## Arquivos que o Kimi criou mas cujo conteúdo NÃO temos (recriar do zero)
| Arquivo | Descrição declarada pelo Kimi |
|---|---|
| pyproject.toml | Config do projeto com dependências |
| .env.example | Template de configuração |
| crypto_bot/__init__.py | Pacote Python |
| crypto_bot/config.py | Pydantic Settings — config centralizada |
| crypto_bot/schema/candles.sql | Schema OHLCV com constraints temporais |
| crypto_bot/schema/features.sql | Schema de features (30+ campos) |
| crypto_bot/schema/regimes.sql | Schema de regime detection |
| crypto_bot/schema/signals.sql | Candidatos aprovados E rejeitados |
| crypto_bot/schema/trades.sql | Audit trail de trades |
| crypto_bot/schema/meta_labels.sql | Dados de treino p/ meta-labeling |
| crypto_bot/storage/database.py | DuckDB com migrations versionadas, backups, dedup |
| crypto_bot/collectors/candles.py | Coleta 24/7 com validação, gap detection, retry, backfill |

> Se o usuário tiver baixado esses arquivos do Kimi, eles estarão numa pasta `kimi_download/`. Se a pasta não existir, RECRIE esses módulos seguindo a interface implícita usada pelos módulos de referência (ex.: `db.query()`, `db.execute()`, `db.insert_dataframe()`, `db.get_candle_count()`, `db.get_last_candle_timestamp()`, `SETTINGS.symbols`, `SETTINGS.timeframes`, `SETTINGS.telegram.*`, `SETTINGS.collection.interval_seconds`, `SETTINGS.paper_trading.enabled`, `CandleCollector.collect_all()` async retornando dict symbol→int com -1 em erro, `.close()`).

## Arquivos disponíveis em `kimi_reference/` (verbatim do chat)
| Arquivo | Papel |
|---|---|
| labeller.py | Rotulagem temporal strict (anti look-ahead) — future_return_15m/30m/1h/4h/1d |
| health.py | Data Quality Gate — valida dados antes de qualquer decisão |
| alerts.py | Alertas Telegram (httpx async) |
| main.py | Orquestrador 24/7 (ciclo: coleta → label → health → alerta) |
| technical.py | Feature engineering (RSI, MAs, BB, ATR, momentum, volume, OBV, price action) |
| rules_detector.py | Regime detection por regras (ADX proxy, ATR percentil, volume, momentum, composite) |

## ⚠️ BUGS CONHECIDOS nos arquivos de referência (corrigir na integração)
1. **health.py — gate sempre falha**: `max_age_seconds = 120`, mas candle de 15m tem até 900s de idade (1h → 3600s). Corrigir para tolerância por timeframe: `1.5 × timeframe_seconds + margem`.
2. **alerts.py — Telegram rejeita mensagens**: usa `parse_mode: MarkdownV2` sem escapar caracteres reservados (`.`, `-`, `(`, `)`, `!` etc.). Corrigir: escapar via função utilitária ou usar `parse_mode: HTML`.
3. **main.py — quebra em Python 3.12**: `asyncio.get_event_loop().add_signal_handler()` chamado no `__init__`, fora de um loop rodando. Corrigir: registrar handlers dentro de `run()` via `asyncio.get_running_loop()`.
4. **technical.py — dependência TA-Lib**: biblioteca C difícil de instalar. Substituir por `pandas-ta` ou implementação manual (numpy/pandas) mantendo os mesmos nomes de colunas.
5. **labeller.py — risco de duplicatas**: `insert_dataframe(..., if_exists="append")` sem upsert; se o batch reprocessar, duplica. Corrigir: `INSERT ... ON CONFLICT DO NOTHING` (candle_id é PK) ou anti-join antes do insert.
6. **labeller.py — filtro conservador demais**: só rotula candles com mais de 2 dias, mas o horizonte máximo é 1d. Ajustar para `now - (maior horizonte + 1 candle)` para rotular mais cedo.
7. **rules_detector.py — colunas acopladas**: espera `atr_14`, `volume_sma_20`, `momentum_10`, `ma_20` já presentes no df de entrada (saída do technical.py joined com candles). Documentar/garantir esse contrato no pipeline.

## Decisões de arquitetura já tomadas (não rediscutir)
- **Mercado**: Binance Futures perpétuos (USDT-M) — permite short e coleta de funding rate. Endpoints públicos na fase de pesquisa, sem API key.
- **Banco**: DuckDB com migrations versionadas + backup diário.
- **Filosofia**: sistema ADAPTATIVO, sem estratégia fixa — 3 camadas: (1) regime detection lê o mercado, (2) pesos online (multiplicative weights por regime) aprendem quais voters funcionam agora, (3) meta-labeling (XGBoost) aprende a filtrar/dimensionar sinais.
- **Anti look-ahead é inegociável**: labeller strict, walk-forward, nunca otimizar no conjunto de teste.
- **Custos como filtro**: sinal só vira trade se edge estimado > 2 × (taxa + slippage médio).
- **Métricas norte**: expectância líquida por trade e Sharpe — NÃO hit rate isolado.
- **Nenhuma ordem executada** (nem testnet) até fase de execução liberada explicitamente pelo usuário.

## Ordem de trabalho para o Claude Code
1. Montar o esqueleto do pacote e recriar os 12 arquivos sem conteúdo (ou integrar `kimi_download/` se existir)
2. Integrar os 6 módulos de `kimi_reference/` CORRIGINDO os 7 bugs acima
3. Escrever testes pytest (validator, labeller anti-look-ahead, quality gate, regime detector)
4. Rodar o sistema em modo coleta e validar 1 ciclo completo ponta a ponta
5. Só então seguir o ROADMAP para os módulos de negócio (voters, backtest walk-forward, pesos online, meta-labeling)
