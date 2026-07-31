-- Audit trail de trades (paper primeiro; execução real BLOQUEADA até liberação explícita)
CREATE SEQUENCE IF NOT EXISTS seq_trades_id START 1;

CREATE TABLE IF NOT EXISTS trades (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_trades_id'),
    signal_id BIGINT REFERENCES signals(id),
    symbol VARCHAR(30) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    is_paper BOOLEAN NOT NULL DEFAULT TRUE,
    entry_ts TIMESTAMPTZ,
    entry_price DOUBLE,
    exit_ts TIMESTAMPTZ,
    exit_price DOUBLE,
    size DOUBLE,
    fee_paid DOUBLE,
    slippage DOUBLE,
    pnl_gross DOUBLE,
    pnl_net DOUBLE,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
