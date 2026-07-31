-- Candidatos a sinal — aprovados E rejeitados (auditabilidade total)
-- Preenchido nas fases futuras (voters/ensemble). Schema criado desde já.
CREATE SEQUENCE IF NOT EXISTS seq_signals_id START 1;

CREATE TABLE IF NOT EXISTS signals (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_signals_id'),
    candle_id BIGINT REFERENCES candles(id),
    symbol VARCHAR(30) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    voter VARCHAR(50) NOT NULL,
    direction VARCHAR(10) NOT NULL,          -- LONG / SHORT / FLAT
    confidence DOUBLE,
    regime_composite VARCHAR(80),
    approved BOOLEAN NOT NULL,
    rejection_reason VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
