-- Features técnicas por candle (saída de features/technical.py)
CREATE TABLE IF NOT EXISTS features (
    candle_id BIGINT PRIMARY KEY REFERENCES candles(id),
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    rsi_14 DOUBLE,
    rsi_7 DOUBLE,
    ma_20 DOUBLE,
    ma_50 DOUBLE,
    ma_200 DOUBLE,
    ema_12 DOUBLE,
    ema_26 DOUBLE,
    bb_upper DOUBLE,
    bb_middle DOUBLE,
    bb_lower DOUBLE,
    bb_width DOUBLE,
    atr_14 DOUBLE,
    atr_percent DOUBLE,
    momentum_10 DOUBLE,
    momentum_20 DOUBLE,
    volatility_20 DOUBLE,
    volatility_50 DOUBLE,
    volume_sma_20 DOUBLE,
    volume_ratio DOUBLE,
    obv DOUBLE,
    body_size DOUBLE,
    upper_shadow DOUBLE,
    lower_shadow DOUBLE,
    range_pct DOUBLE,
    calculated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_features_lookup ON features (symbol, timeframe, timestamp);
