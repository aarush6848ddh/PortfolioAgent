#!/usr/bin/env python3
"""Self-heal check for scheduled agent digests.

A scheduled run (e.g. the Saturday weekly digest) can die mid-pipeline during a
WiFi roam-flap: the process hangs, never records a finished_at, and never sends
its Telegram message — leaving a dangling status='running' row. That is exactly
what happened to the 2026-07-25 weekly digest.

Cron fires this shortly after the scheduled run to detect that case (a stuck
'running' row) OR an outright missing run, and re-trigger the digest.

Usage:  python self_heal.py <mode> [--dry-run]
        e.g. python self_heal.py weekly

Idempotent: if a successful run for <mode> already exists today, it exits
without doing anything, so it is safe to schedule more than once.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta

import pytz

from portfolio import get_conn

ET = pytz.timezone("America/New_York")
STUCK_AFTER_MIN = 20        # a 'running' row this old with no finished_at = dead
RERUN_TIMEOUT_SEC = 900     # don't let a re-triggered run hang self_heal forever
HERE = os.path.dirname(os.path.abspath(__file__))


def run_is_stuck(status, finished_at, started_at, now):
    """A run is 'stuck' when it claims to still be running but hasn't updated in
    a long time — the hallmark of a process that hung/died without recording an
    end (the 2026-07-25 weekly failure fingerprint)."""
    if status != "running" or finished_at is not None:
        return False
    return started_at.astimezone(ET) < now - timedelta(minutes=STUCK_AFTER_MIN)


def main():
    mode = "weekly"
    dry_run = False
    for arg in sys.argv[1:]:
        if arg == "--dry-run":
            dry_run = True
        else:
            mode = arg.lstrip("-")

    now = datetime.now(ET)
    today = now.date()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, status, started_at, finished_at
             FROM agent_runs
            WHERE mode = %s
              AND (started_at AT TIME ZONE 'America/New_York')::date = %s
            ORDER BY started_at""",
        (mode, today),
    )
    rows = cur.fetchall()

    # 1. Already succeeded today → digest went out, nothing to do.
    if any(r[1] == "success" for r in rows):
        print(f"[self_heal] {mode}: successful run already recorded today — OK, no action")
        conn.close()
        return

    # 2. Mark any stuck 'running' rows as failed so the table stays honest and
    #    the dangling state doesn't linger (matches: "treat that as a failed run").
    stuck = [r for r in rows if run_is_stuck(r[1], r[3], r[2], now)]
    for r in stuck:
        print(f"[self_heal] {mode}: run id={r[0]} stuck in 'running' since "
              f"{r[2].astimezone(ET):%Y-%m-%d %H:%M %Z} — marking failed")
        if not dry_run:
            cur.execute(
                "UPDATE agent_runs SET status='failed', finished_at=NOW(), error=%s WHERE id=%s",
                ("stale: no finished_at, marked failed by self_heal", r[0]),
            )
    if not dry_run:
        conn.commit()

    # 3. If a run is genuinely still in progress (fresh 'running', < STUCK_AFTER_MIN),
    #    don't pile on with a duplicate — let it finish.
    fresh_running = [r for r in rows
                     if r[1] == "running" and r[3] is None and r not in stuck]
    if fresh_running:
        print(f"[self_heal] {mode}: a run is still in progress (fresh 'running') — "
              f"not re-triggering, letting it finish")
        conn.close()
        return

    conn.close()

    # 4. No success, nothing fresh in progress → the digest did not go out today.
    #    Covers all failure shapes: no row at all, stuck-then-failed, or failed.
    reason = "stuck run (hung/died)" if stuck else ("no run recorded" if not rows else "prior run failed")
    print(f"[self_heal] {mode}: no successful run today ({reason}) — re-triggering agent.py --{mode}")
    if dry_run:
        print(f"[self_heal] {mode}: DRY RUN — would run: {sys.executable} agent.py --{mode}")
        return

    try:
        subprocess.run(
            [sys.executable, "agent.py", f"--{mode}"],
            cwd=HERE, check=False, timeout=RERUN_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"[self_heal] {mode}: re-triggered run exceeded {RERUN_TIMEOUT_SEC}s and was killed")


if __name__ == "__main__":
    main()
