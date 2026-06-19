-- Agent logs: every reasoning run, sent or not
CREATE TABLE IF NOT EXISTS agent_logs (
    id SERIAL PRIMARY KEY,
    run_type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    response TEXT NOT NULL,
    sent BOOLEAN NOT NULL DEFAULT FALSE,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Daily closes: one row per ticker per day, for quant analysis
CREATE TABLE IF NOT EXISTS daily_closes (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    open_price NUMERIC,
    high_price NUMERIC,
    low_price NUMERIC,
    close_price NUMERIC NOT NULL,
    volume BIGINT,
    UNIQUE(ticker, date)
);

-- Index on prices for faster lookups
CREATE INDEX IF NOT EXISTS idx_prices_ticker_recorded ON prices (ticker, recorded_at DESC);

-- Index on daily_closes for time-series queries
CREATE INDEX IF NOT EXISTS idx_daily_closes_ticker_date ON daily_closes (ticker, date DESC);
