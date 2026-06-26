-- Decision memory: stores takeaways from each run for context injection
CREATE TABLE IF NOT EXISTS decision_memory (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    run_type TEXT NOT NULL,
    takeaways TEXT NOT NULL,
    portfolio_value NUMERIC,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Target allocation: user-defined target weights for drift detection
CREATE TABLE IF NOT EXISTS target_allocation (
    ticker TEXT PRIMARY KEY,
    target_pct NUMERIC NOT NULL
);

-- Dividend history: auto-tracked from Finnhub
CREATE TABLE IF NOT EXISTS dividends (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    ex_date DATE,
    pay_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_decision_memory_date ON decision_memory (date DESC);
CREATE INDEX IF NOT EXISTS idx_dividends_ticker ON dividends (ticker, ex_date DESC);
