# Cole isto no Claude Code (a pasta já deve conter CLAUDE.md, STATUS.md, ROADMAP.md e kimi_reference/)

---

Leia CLAUDE.md, STATUS.md e ROADMAP.md antes de escrever qualquer código. Este projeto foi iniciado por outra IA (Kimi) e interrompido no meio; o STATUS.md documenta exatamente o que existe, o que falta e 7 bugs conhecidos. Sua missão é completar a fase de PESQUISA (coleta + rotulagem + features + regimes), sem executar nenhuma ordem.

Trabalhe nesta ordem, com um commit por etapa e testes antes de cada commit:

## Etapa 1 — Fundação
Crie o esqueleto do pacote conforme CLAUDE.md: pyproject.toml, .env.example, config.py (pydantic-settings com a interface descrita no STATUS.md: SETTINGS.symbols, SETTINGS.timeframes, SETTINGS.telegram.*, SETTINGS.collection.interval_seconds, SETTINGS.paper_trading.enabled), schemas SQL e storage/database.py (DuckDB com migrations versionadas, método insert com dedup/upsert, backup diário, e os helpers query/execute/insert_dataframe/get_candle_count/get_last_candle_timestamp usados pelos módulos de referência).

## Etapa 2 — Coleta
Implemente collectors/candles.py: coleta OHLCV 15m/1h/4h de BTC, ETH e SOL perpétuos (Binance Futures USDT-M via CCXT, endpoints públicos), com validação (gaps, OHLC inconsistente, volume zero), retry com backoff exponencial, backfill de 30 dias no primeiro boot, e collect_all() async retornando dict symbol→candles_inseridos (-1 em erro). Teste com mock da API.

## Etapa 3 — Integração dos módulos de referência (CORRIGINDO os bugs)
Copie cada arquivo de kimi_reference/ para o destino indicado em kimi_reference/_LEIA-ME.md, corrigindo os 7 bugs do STATUS.md:
1. health.py: tolerância de idade por timeframe (1.5 × tf_seconds + 60s), não 120s fixo
2. alerts.py: trocar MarkdownV2 por HTML com escape adequado
3. main.py: signal handlers dentro de run() via get_running_loop()
4. technical.py: remover talib — implementar RSI, SMA/EMA, Bollinger, ATR, MOM, OBV em pandas/numpy mantendo os mesmos nomes de colunas
5. labeller.py: upsert/anti-join em vez de append cego
6. labeller.py: janela de rotulagem = maior horizonte + 1 candle (não 2 dias fixos)
7. Pipeline: garantir que rules_detector receba o df com candles + features joinados (documentar o contrato)

## Etapa 4 — Testes críticos
- Teste anti look-ahead do labeller com dados sintéticos: injete um candle futuro com preço absurdo e prove que ele NÃO vaza para labels de candles anteriores ao horizonte
- Teste do quality gate: cenários fresh/stale/gap
- Teste do regime detector: séries sintéticas de tendência clara e lateralização devem produzir os regimes esperados

## Etapa 5 — Rodar ponta a ponta
Suba o main.py em modo coleta, execute pelo menos 2 ciclos completos reais (coleta → features → regime → label → health) e me mostre: contagem de candles por par/timeframe, amostra de features, distribuição de regimes e confirmação de zero gaps. Depois crie deploy/cryptobot.service (systemd, Restart=on-failure) e README com instruções de operação.

## Regras
- Nada em execution/ — nenhuma ordem, nem testnet
- Se encontrar ambiguidade não coberta pelos documentos, pergunte antes de assumir
- Ao final de cada etapa, resuma o que foi feito e o que vem a seguir
