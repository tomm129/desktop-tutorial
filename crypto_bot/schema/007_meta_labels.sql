-- Dados de treino para meta-labeling (fase futura — XGBoost filtra/dimensiona sinais)
CREATE TABLE IF NOT EXISTS meta_labels (
    signal_id BIGINT PRIMARY KEY REFERENCES signals(id),
    candle_id BIGINT REFERENCES candles(id),
    symbol VARCHAR(30),
    timeframe VARCHAR(10),
    timestamp TIMESTAMPTZ,
    regime_composite VARCHAR(80),
    funding_rate DOUBLE,
    orderbook_imbalance DOUBLE,
    hour_of_day INTEGER,
    day_of_week INTEGER,
    outcome_return DOUBLE,
    outcome_hit BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
