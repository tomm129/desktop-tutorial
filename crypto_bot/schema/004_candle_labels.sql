-- Rótulos temporais estritos (saída de research/labeller.py)
CREATE TABLE IF NOT EXISTS candle_labels (
    candle_id BIGINT PRIMARY KEY REFERENCES candles(id),
    symbol VARCHAR(30),
    timeframe VARCHAR(10),
    timestamp TIMESTAMPTZ,
    signal_price DOUBLE,
    future_return_15m DOUBLE,
    future_return_30m DOUBLE,
    future_return_1h DOUBLE,
    future_return_4h DOUBLE,
    future_return_1d DOUBLE,
    label_populated_at TIMESTAMPTZ,
    label_validated BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_labels_lookup ON candle_labels (symbol, timeframe, timestamp);
