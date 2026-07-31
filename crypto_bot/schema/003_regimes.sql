-- Regimes de mercado por candle (saída de features/regime/rules_detector.py)
CREATE TABLE IF NOT EXISTS regimes (
    candle_id BIGINT PRIMARY KEY REFERENCES candles(id),
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    trend VARCHAR(20),
    volatility VARCHAR(20),
    volume_state VARCHAR(20),
    momentum_state VARCHAR(20),
    composite VARCHAR(80),
    detected_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_regimes_lookup ON regimes (symbol, timeframe, timestamp);
