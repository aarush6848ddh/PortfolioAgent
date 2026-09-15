# TODO / Follow-ups

## Quant / metrics

- [ ] **Backfill 8 missing `sale_price` values in `holdings`.** 6 of 14 closed
  positions have `sale_price`; 8 are NULL, so `/portfolio/quant-metrics`
  `total_return_pct` is explicitly partial (`total_return_partial: true`,
  `priced_closed_positions: 6 / total_closed_positions: 14`). These must be
  entered manually from the actual trade confirmations — they are not
  computable from anything in the DB. Once populated, the partial caveat
  clears automatically.

- [ ] **Fix mislabeled "total deposited" (`orchestrator.py:301`).** The weekly
  report calls `get_total_contributions()` "Your money (total deposited)", but
  the `contributions` table is actually a buy-transaction log (rows read e.g.
  `"Buy 0.587 QQQM @ $174.72"`), not external cash deposits, and some buys were
  funded by sale proceeds. The figure is not deposits. Needs a real cashflow
  ledger that separates external deposits/withdrawals from internal buys/sells.

- [ ] **(Future refinement) Time-weight drawdown / return by actually-held
  periods.** The `/portfolio/quant-metrics` return-index drawdown weights each
  ticker by *current* share counts across the whole window, inventing weights
  for pre-purchase periods. A proper fix reconstructs holdings-over-time. Low
  priority vs. the above; the current method already avoids the far worse
  raw-snapshot cashflow artifact (a sell showed as a fake -63% drawdown).

- [ ] **Wire dividend income into `total_return` (fix #5 item 2 deferral).** The
  `dividends` table is now populated (98 per-share events from yfinance, current
  + past holdings), but nothing consumes it — returns are still price-only. To
  fold in income correctly you need *shares held at each ex-date* (ex-date ×
  shares-then), which is the same holdings-over-time reconstruction as the item
  above. Deliberately not approximated with current shares (would invent income
  for pre-purchase quarters). Blocked on holdings-over-time.

- [ ] **Unify `recovery_days` units across the two paths.** Same class of bug as
  the fix #4 consolidation (two paths measuring one concept differently), left
  out of scope for that pass. After a max-drawdown trough, `quant.py`
  (`calc_portfolio_drawdown`) reports recovery in *calendar* days
  (`(recovery_date - trough_date).days`), while `api/main.py`
  (`/portfolio/quant-metrics`) reports the *trading-day* index offset. On live
  data these read 15 vs 10 for the identical recovery point, which is confusing
  side by side. Pick one convention (calendar days is the more intuitive
  display) and route both through it.
