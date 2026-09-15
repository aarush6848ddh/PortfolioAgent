BEGIN;

-- 1. Merge duplicate open positions into the oldest row, weighted-average basis
WITH dups AS (
    SELECT ticker,
           MIN(id)                                AS keep_id,
           SUM(shares)                            AS total_shares,
           SUM(shares * cost_basis) / SUM(shares) AS avg_basis
    FROM holdings
    WHERE sold_at IS NULL
    GROUP BY ticker
    HAVING COUNT(*) > 1
)
UPDATE holdings h
SET shares = d.total_shares, cost_basis = d.avg_basis
FROM dups d
WHERE h.id = d.keep_id;

-- 2. Delete the now-merged duplicate rows
DELETE FROM holdings h
USING (
    SELECT ticker, MIN(id) AS keep_id
    FROM holdings
    WHERE sold_at IS NULL
    GROUP BY ticker
    HAVING COUNT(*) > 1
) d
WHERE h.ticker = d.ticker
  AND h.sold_at IS NULL
  AND h.id <> d.keep_id;

-- 3. DB-enforced invariant: one open position per ticker
CREATE UNIQUE INDEX one_open_position_per_ticker
    ON holdings (ticker) WHERE sold_at IS NULL;

-- 4. Run-outcome table (agent_logs already exists for LLM prompt/response)
CREATE TABLE IF NOT EXISTS agent_runs (
    id          SERIAL PRIMARY KEY,
    mode        TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status      TEXT NOT NULL DEFAULT 'running',  -- running|success|silent|skipped|failed
    error       TEXT
);

COMMIT;
