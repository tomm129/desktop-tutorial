-- Candles OHLCV com constraints de integridade temporal e de preço
CREATE SEQUENCE IF NOT EXISTS seq_candles_id START 1;

CREATE TABLE IF NOT EXISTS candles (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_candles_id'),
    symbol VARCHAR(30) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DOUBLE NOT NULL CHECK (open > 0),
    high DOUBLE NOT NULL CHECK (high > 0),
    low DOUBLE NOT NULL CHECK (low > 0),
    close DOUBLE NOT NULL CHECK (close > 0),
    volume DOUBLE NOT NULL CHECK (volume >= 0),
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (high >= low),
    CHECK (high >= open AND high >= close),
    CHECK (low <= open AND low <= close),
    UNIQUE (symbol, timeframe, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles (symbol, timeframe, timestamp);
