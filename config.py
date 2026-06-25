"""Centralized configuration for PortfolioAgent.
All thresholds and limits in one place — override via env vars."""
import os

# Concentration alert
CONCENTRATION_BASE_PCT = float(os.environ.get("CONCENTRATION_BASE_PCT", "50"))
CONCENTRATION_STEP_PCT = float(os.environ.get("CONCENTRATION_STEP_PCT", "5"))

# Big move threshold (daily % change to trigger alert)
BIG_MOVE_PCT = float(os.environ.get("BIG_MOVE_PCT", "3.0"))

# Portfolio drawdown alert threshold (% below cost basis)
DRAWDOWN_ALERT_PCT = float(os.environ.get("DRAWDOWN_ALERT_PCT", "5.0"))

# Fear & Greed sustained fear alert
FEAR_THRESHOLD = int(os.environ.get("FEAR_THRESHOLD", "30"))
FEAR_SUSTAINED_DAYS = int(os.environ.get("FEAR_SUSTAINED_DAYS", "5"))

# Message word limits
INTRADAY_WORD_LIMIT = int(os.environ.get("INTRADAY_WORD_LIMIT", "100"))
MORNING_WORD_LIMIT = int(os.environ.get("MORNING_WORD_LIMIT", "150"))

# Drift detection threshold (% deviation from target allocation)
DRIFT_ALERT_PCT = float(os.environ.get("DRIFT_ALERT_PCT", "10.0"))

# Health check
HEALTH_CHECK_PORT = int(os.environ.get("HEALTH_CHECK_PORT", "8111"))

# Monte Carlo
MONTE_CARLO_SIMULATIONS = int(os.environ.get("MONTE_CARLO_SIMULATIONS", "1000"))
MONTE_CARLO_DAYS = int(os.environ.get("MONTE_CARLO_DAYS", "252"))
