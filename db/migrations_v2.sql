-- Alert state: tracks last alerted threshold to prevent repeat alerts
CREATE TABLE IF NOT EXISTS alert_state (
    alert_type TEXT PRIMARY KEY,
    last_threshold NUMERIC,
    last_alerted_at TIMESTAMP DEFAULT NOW()
);

-- Daily portfolio snapshots: powers weekly digest
CREATE TABLE IF NOT EXISTS daily_snapshots (
    date DATE PRIMARY KEY,
    total_value NUMERIC NOT NULL,
    total_cost NUMERIC NOT NULL,
    day_pl NUMERIC,
    fear_greed_score NUMERIC
);

-- Contributions: tracks money deposited separately from gains
CREATE TABLE IF NOT EXISTS contributions (
    id SERIAL PRIMARY KEY,
    amount NUMERIC NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Fear & Greed history: daily tracking for sustained fear alerts
CREATE TABLE IF NOT EXISTS fear_greed_history (
    date DATE PRIMARY KEY,
    score NUMERIC NOT NULL,
    rating TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_daily_snapshots_date ON daily_snapshots (date DESC);
CREATE INDEX IF NOT EXISTS idx_fear_greed_history_date ON fear_greed_history (date DESC);
