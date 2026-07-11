"""Multi-agent orchestrator using LangGraph.

Six specialist agents — data, news, quant run in parallel, then bull/bear debate,
then synthesis combines everything:

  [START] ──┬── data_agent ───┐
             ├── news_agent ───┼──┬── bull_agent ──┐
             └── quant_agent ──┘  └── bear_agent ──┼── synthesis_agent ── [END]
"""
import os
from datetime import datetime, timedelta, date
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv

from portfolio import (
    get_holdings, get_finnhub_quote, get_prev_close, get_streak,
    store_daily_close, get_conn, SYSTEM_PROMPT, sanitize_response,
    get_alert_threshold, set_alert_threshold,
    store_daily_snapshot, get_weekly_snapshots, get_last_week_snapshots,
    get_yesterday_closes, get_total_contributions, get_total_dividends,
    get_recent_decisions, store_decision_memory,
    get_target_allocations, ET,
)
from quant import get_quant_summary, format_quant_for_prompt
from news import get_full_intel
from sentiment import (
    get_fear_greed, format_fear_greed,
    store_fear_greed, check_sustained_fear, get_avg_fear_greed,
)
from config import (
    CONCENTRATION_BASE_PCT, CONCENTRATION_STEP_PCT,
    BIG_MOVE_PCT, DRAWDOWN_ALERT_PCT, DRIFT_ALERT_PCT,
    INTRADAY_WORD_LIMIT, MORNING_WORD_LIMIT,
)

load_dotenv()

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.3)

import time
import logging

log = logging.getLogger("orchestrator")

def llm_invoke_with_retry(messages, max_retries=3):
    """Call LLM with retry on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return llm.invoke(messages)
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 10 * (attempt + 1)
                log.warning(f"Rate limited, waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    return llm.invoke(messages)  # final attempt, let it raise


# --- State ---

def merge_str(existing: str, new: str) -> str:
    return new if new else existing

class AgentState(TypedDict):
    mode: Annotated[str, merge_str]
    question: Annotated[str, merge_str]
    holdings: list
    data_report: Annotated[str, merge_str]
    news_report: Annotated[str, merge_str]
    quant_report: Annotated[str, merge_str]
    bull_report: Annotated[str, merge_str]
    bear_report: Annotated[str, merge_str]
    synthesis: Annotated[str, merge_str]

# --- Agent Nodes ---

def data_agent(state: AgentState) -> dict:
    """Gathers portfolio snapshot — prices, P&L, streaks, allocation,
    performance attribution, threshold alerts, drift detection."""
    holdings = state["holdings"]
    mode = state["mode"]

    if not holdings:
        return {"data_report": "No positions in portfolio."}

    lines = []
    total_value = 0.0
    total_cost = 0.0
    total_day_pl = 0.0
    attribution = []
    alerts = []
    big_move_tickers = []

    # Fetch each quote once and reuse (avoids double Finnhub calls per holding)
    ticker_quotes = {h["ticker"]: get_finnhub_quote(h["ticker"]) for h in holdings}

    for h in holdings:
        quote = ticker_quotes[h["ticker"]]
        prev = get_prev_close(h["ticker"])
        streak = get_streak(h["ticker"])

        price = quote["current"] if quote else prev
        if price is None:
            lines.append(f"{h['ticker']}: no price data")
            continue

        value = price * h["shares"]
        cost = h["cost_basis"] * h["shares"]
        total_value += value
        total_cost += cost
        pl = value - cost
        pl_pct = (price - h["cost_basis"]) / h["cost_basis"] * 100

        parts = [
            f"{h['ticker']}: {h['shares']} shares @ ${h['cost_basis']:.2f}",
            f"now ${price:.2f}",
            f"P&L: ${pl:.2f} ({pl_pct:+.1f}%)",
        ]

        # Only report streaks of 3+ consecutive days
        if abs(streak) >= 3:
            streak_str = f"{abs(streak)}-day {'up' if streak > 0 else 'down'} streak"
            parts.append(streak_str)

        if quote:
            parts.append(f"today: {quote['change_pct']:+.2f}%")
            parts.append(f"range: ${quote['low']:.2f}-${quote['high']:.2f}")
            day_pl = (quote["current"] - quote["prev_close"]) * h["shares"]
            total_day_pl += day_pl
            attribution.append({"ticker": h["ticker"], "day_pl": day_pl})

            if abs(quote["change_pct"]) >= BIG_MOVE_PCT:
                alerts.append(f"BIG MOVE: {h['ticker']} is {'up' if quote['change_pct'] > 0 else 'down'} {abs(quote['change_pct']):.1f}% today")
                big_move_tickers.append(h["ticker"])

            if mode == "daily":
                store_daily_close(h["ticker"], price)

        lines.append(" | ".join(parts))

    # Store SPY close (daily mode)
    if mode == "daily":
        spy_quote = get_finnhub_quote("SPY")
        if spy_quote:
            store_daily_close("SPY", spy_quote["current"])

    # Allocation + concentration check (threshold stepping)
    alloc = []
    current_alloc = {}
    for h in holdings:
        q = ticker_quotes[h["ticker"]]
        p = q["current"] if q else get_prev_close(h["ticker"])
        if p and total_value > 0:
            weight = (p * h["shares"]) / total_value * 100
            alloc.append(f"{h['ticker']}: {weight:.1f}%")
            current_alloc[h["ticker"]] = weight

            if weight > CONCENTRATION_BASE_PCT:
                current_step = int(weight // CONCENTRATION_STEP_PCT) * CONCENTRATION_STEP_PCT
                last_step = get_alert_threshold(f"concentration_{h['ticker']}")
                if last_step is None or current_step > float(last_step):
                    alerts.append(f"CONCENTRATION: {h['ticker']} is {weight:.0f}% of your portfolio")
                    set_alert_threshold(f"concentration_{h['ticker']}", current_step)
            else:
                if get_alert_threshold(f"concentration_{h['ticker']}"):
                    set_alert_threshold(f"concentration_{h['ticker']}", 0)

    lines.append(f"Allocation: {', '.join(alloc)}")
    lines.append(f"Total: ${total_value:.2f} | Cost: ${total_cost:.2f} | P&L: ${total_value - total_cost:+.2f} | Day P&L: ${total_day_pl:+.2f}")

    # Drift detection (target allocation)
    targets = get_target_allocations()
    if targets and current_alloc:
        drift_alerts = []
        for ticker, target in targets.items():
            actual = current_alloc.get(ticker, 0)
            drift = actual - target
            if abs(drift) >= DRIFT_ALERT_PCT:
                direction = "overweight" if drift > 0 else "underweight"
                drift_alerts.append(f"DRIFT: {ticker} is {direction} by {abs(drift):.1f}pp (target: {target:.0f}%, actual: {actual:.1f}%)")
        alerts.extend(drift_alerts)

    # Drawdown from peak
    if total_cost > 0:
        portfolio_return = (total_value - total_cost) / total_cost * 100
        if portfolio_return < -DRAWDOWN_ALERT_PCT:
            alerts.append(f"DRAWDOWN: portfolio is down {portfolio_return:.1f}% from your total cost basis")

    # Performance attribution
    if attribution:
        attribution.sort(key=lambda x: abs(x["day_pl"]), reverse=True)
        attr_lines = [f"  {a['ticker']}: ${a['day_pl']:+.2f}" for a in attribution]
        lines.append(f"\nDay's P&L breakdown (who moved your money):")
        lines.extend(attr_lines)

    # Big move flag for synthesis
    if big_move_tickers:
        lines.append(f"\nBIG_MOVE_TICKERS: {', '.join(big_move_tickers)}")
    else:
        lines.append(f"\nBIG_MOVE_TICKERS: NONE")

    # Beta explanation flag — only explain beta when SOXX moves > 3% in a day
    soxx_quote = ticker_quotes.get("SOXX")
    beta_explain = soxx_quote and abs(soxx_quote["change_pct"]) > 3.0
    lines.append(f"\nBETA_EXPLAIN: {'YES' if beta_explain else 'NO'}")

    # Fear & Greed Index
    fg = get_fear_greed()
    lines.append(f"\n{format_fear_greed(fg)}")

    # Store F&G daily
    if fg:
        store_fear_greed(fg["score"], fg["rating"])

    # Check sustained fear
    fear_alert = check_sustained_fear()
    if fear_alert:
        alerts.append(fear_alert)

    # Threshold alerts
    if alerts:
        lines.append(f"\n=== ALERTS ===")
        for a in alerts:
            lines.append(f"  ! {a}")

    # --- Mode-specific sections ---

    # Morning: yesterday's close only (weekly summary moved to Friday EOD)
    if mode == "morning":
        yesterday = get_yesterday_closes([h["ticker"] for h in holdings])
        if yesterday:
            lines.append("\n=== YESTERDAY'S CLOSE ===")
            for ticker, data in yesterday.items():
                lines.append(f"  {ticker}: ${data['price']:.2f} ({data['date']})")

    # Friday EOD: weekly stats for the dedicated Friday digest
    if mode == "friday_eod":
        fg_score = fg["score"] if fg else None
        store_daily_snapshot(total_value, total_cost, total_day_pl, fg_score)
        snapshots = get_weekly_snapshots()
        if snapshots:
            week_pl = sum(s["day_pl"] for s in snapshots)
            best_day = max(snapshots, key=lambda s: s["day_pl"])
            worst_day = min(snapshots, key=lambda s: s["day_pl"])
            fg_scores = [s["fg_score"] for s in snapshots if s["fg_score"] is not None]
            avg_fg = round(sum(fg_scores) / len(fg_scores), 1) if fg_scores else None

            lines.append(f"\n=== WEEKLY STATS ===")
            lines.append(f"  Week P&L: ${week_pl:+.2f}")
            lines.append(f"  Best day: {best_day['date']} (${best_day['day_pl']:+.2f})")
            lines.append(f"  Worst day: {worst_day['date']} (${worst_day['day_pl']:+.2f})")
            if avg_fg:
                lines.append(f"  Average Fear & Greed: {avg_fg}/100")

    # Daily: store snapshot
    if mode == "daily":
        fg_score = fg["score"] if fg else None
        store_daily_snapshot(total_value, total_cost, total_day_pl, fg_score)

    # Weekly: aggregate stats + contributions + dividends
    if mode == "weekly":
        snapshots = get_weekly_snapshots()
        if snapshots:
            week_pl = sum(s["day_pl"] for s in snapshots)
            best_day = max(snapshots, key=lambda s: s["day_pl"])
            worst_day = min(snapshots, key=lambda s: s["day_pl"])
            fg_scores = [s["fg_score"] for s in snapshots if s["fg_score"] is not None]
            avg_fg = round(sum(fg_scores) / len(fg_scores), 1) if fg_scores else None

            lines.append(f"\n=== WEEKLY STATS ===")
            lines.append(f"  Week P&L: ${week_pl:+.2f}")
            lines.append(f"  Best day: {best_day['date']} (${best_day['day_pl']:+.2f})")
            lines.append(f"  Worst day: {worst_day['date']} (${worst_day['day_pl']:+.2f})")
            if avg_fg:
                lines.append(f"  Average Fear & Greed: {avg_fg}/100")

        contributions = get_total_contributions()
        dividends = get_total_dividends()
        if contributions > 0:
            gains = total_value - contributions
            lines.append(f"\n=== YOUR MONEY vs MARKET GAINS ===")
            lines.append(f"  Your money (total deposited): ${contributions:.2f}")
            lines.append(f"  Market gains: ${gains:+.2f}")
            if dividends > 0:
                lines.append(f"  Total dividends received: ${dividends:.2f}")

    # Decision history context (for synthesis)
    decisions = get_recent_decisions(limit=5)
    if decisions:
        lines.append(f"\n=== RECENT DECISION MEMORY ===")
        for d in decisions:
            val_str = f" (portfolio: ${d['portfolio_value']:.2f})" if d["portfolio_value"] else ""
            lines.append(f"  [{d['date']}] {d['takeaways']}{val_str}")

    return {"data_report": "\n".join(lines)}


def news_agent(state: AgentState) -> dict:
    """Fetches full market intelligence then uses LLM to synthesize."""
    holdings = state["holdings"]
    if not holdings:
        return {"news_report": "No holdings to analyze."}

    intel_text = get_full_intel(holdings)

    tickers = [h["ticker"] for h in holdings]
    prompt = f"""You are a market intelligence analyst briefing a beginner investor who is
learning how markets work. The portfolio holds: {', '.join(tickers)}.

Analyze this data and produce a concise intelligence report covering:
1. News sentiment — what's the overall tone? Any headline that could move prices?
2. Positioning context — where is each holding relative to its 52-week range?
3. ETF holdings — what are the top holdings driving each ETF? Any notable movers?
4. Economic calendar — any upcoming high-impact events? How could they affect this portfolio?
5. Technical signals — what are the aggregate buy/sell indicators saying? Any key support/resistance levels?
6. Insider/Congressional — any notable insider or congressional trading activity?
7. Social sentiment — any unusual Reddit/Twitter activity on these holdings?
8. Upgrades/Downgrades — any recent analyst rating changes?

When you mention a concept, briefly explain what it means in plain English. Be concise.

End your report with this exact line format:
OVERNIGHT_SENTIMENT: X/10
(1 = very bearish, 5 = neutral, 10 = very bullish, based on overall news/data tone)

{intel_text}"""

    response = llm_invoke_with_retry([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return {"news_report": sanitize_response(response.content)}


def quant_agent(state: AgentState) -> dict:
    """Runs quant analysis including Monte Carlo, then uses LLM to interpret."""
    holdings = state["holdings"]
    if not holdings:
        return {"quant_report": "No holdings to analyze."}

    summary = get_quant_summary(holdings)
    quant_text = format_quant_for_prompt(summary)

    prompt = f"""You are a quantitative analyst explaining portfolio metrics to someone
who is 19 and learning to invest. They're smart but new to finance.

Provide the key metrics and their interpretation:
1. Beta values for each holding
2. Correlation data and what it means for diversification
3. Sharpe/Sortino ratios and whether they're good
4. Drawdown — worst drop and recovery time
5. Backtest — portfolio vs VTI-only approach
6. Monte Carlo simulation — what are the projected outcomes? What does the probability of loss tell us?

State the numbers, then give a brief plain-English interpretation of each.
Keep it factual and concise. Do NOT give investment advice.

{quant_text}"""

    response = llm_invoke_with_retry([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return {"quant_report": sanitize_response(response.content)}


def bull_agent(state: AgentState) -> dict:
    """Makes the strongest bull case for the portfolio based on available data."""
    # Truncate reports for bull/bear to stay within rate limits
    data_short = state['data_report'][:1500]
    news_short = state['news_report'][:1500]
    quant_short = state['quant_report'][:1000]

    prompt = f"""You are a bull case analyst. Based on the data below, make the STRONGEST
possible optimistic case for this portfolio over the next 1-3 months.

Use specific data points: positive news, strong technicals, favorable F&G for buying,
good quant metrics, positive earnings surprises, analyst upgrades, etc.

Be specific and data-driven. No vague optimism — cite numbers from the reports.
Keep it to 4-6 sentences.

=== DATA === {data_short}
=== NEWS === {news_short}
=== QUANT === {quant_short}"""

    response = llm_invoke_with_retry([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return {"bull_report": sanitize_response(response.content)}


def bear_agent(state: AgentState) -> dict:
    """Makes the strongest bear case for the portfolio based on available data."""
    data_short = state['data_report'][:1500]
    news_short = state['news_report'][:1500]
    quant_short = state['quant_report'][:1000]

    prompt = f"""You are a bear case analyst. Based on the data below, make the STRONGEST
possible pessimistic case for this portfolio over the next 1-3 months.

Use specific data points: negative news, weak technicals, high fear readings,
concentration risk, poor earnings outlook, downgrades, macro headwinds, etc.

Be specific and data-driven. No vague pessimism — cite numbers from the reports.
Keep it to 4-6 sentences.

=== DATA === {data_short}
=== NEWS === {news_short}
=== QUANT === {quant_short}"""

    response = llm_invoke_with_retry([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return {"bear_report": sanitize_response(response.content)}


EDUCATOR_RULE = """
IMPORTANT: The user is 19 and learning to invest. When you mention any financial
concept, briefly explain it in plain English.
Don't be condescending — be the smart friend who explains things clearly.
"""

MODE_INSTRUCTIONS = {
    "morning": f"""It's morning, before market open. Synthesize a concise morning briefing.

Structure:
1. Start with yesterday's close for each holding (use the YESTERDAY'S CLOSE data)
2. State the Fear & Greed reading and the overnight news sentiment score
3. One sentence outlook for the day based on beta exposure, Fear & Greed, and news
4. Surface any alerts (including drift alerts)
5. If there are upcoming economic events, flag the most important one
6. Present the bull and bear cases as a "Bulls say / Bears say" two-liner

BETA RULE: Only explain what beta means (e.g. "moves 2.4x the market") if BETA_EXPLAIN is YES. Otherwise just state the beta number without explanation.

HARD LIMIT: {MORNING_WORD_LIMIT} words maximum. Be direct.
{EDUCATOR_RULE}""",

    "intraday": f"""It's during market hours. Synthesize an intraday update.

Rules:
- Put any ALERTS at the very top, clearly labeled
- If there are no alerts AND nothing notable is happening, respond with exactly: SILENT
- Do NOT explain what beta means UNLESS BETA_EXPLAIN is YES. You may state the beta number, but do NOT add any explanation like "moves X times the market" unless BETA_EXPLAIN is YES.
- Do NOT mention 52-week high/low unless a holding actually broke to a new 52-week high TODAY
- Do NOT repeat Sharpe ratio, Sortino, drawdown, backtest, correlation, or Monte Carlo data
- Do NOT include a disclaimer
- Do NOT include any "Bulls say / Bears say" section — intraday messages are facts only, no narrative framing
- Focus on: what moved, by how much, why (connect to news if clear)
- If technical signals are notable (strong buy/sell), mention them briefly

HARD LIMIT: {INTRADAY_WORD_LIMIT} words maximum. Shorter is better.
{EDUCATOR_RULE}""",

    "friday_eod": f"""It's Friday after market close. Synthesize the weekly P&L digest.

This is a dedicated weekly summary. Include ONLY:
1. Total week P&L (from WEEKLY STATS)
2. Best day of the week and worst day of the week (from WEEKLY STATS)
3. Average Fear & Greed for the week
4. A 2-sentence narrative: what drove the week's performance and one thing to watch next week

Do NOT include bulls/bears, quant metrics, Monte Carlo, or individual holding breakdowns.
Keep it tight — this is a recap, not a briefing.
{EDUCATOR_RULE}""",

    "daily": f"""It's end of day. Synthesize a daily summary:
- Start with how much the portfolio made or lost today (total and per-holding attribution)
- Who was the biggest mover and why (connect to news)
- Include the Fear & Greed reading
- Note any alerts (including drift)
- Present the bull/bear cases as a brief "Bulls say / Bears say" section
- Keep it to 6-8 sentences.
{EDUCATOR_RULE}""",

    "weekly": f"""It's the weekend. Synthesize a weekly digest.

Required sections:
1. Total week P&L (from WEEKLY STATS)
2. Best day and worst day (from WEEKLY STATS)
3. Average Fear & Greed for the week
4. YOUR MONEY vs MARKET GAINS — show how much was deposited vs how much the market added. Include dividends if present.
5. How the portfolio stacks up against just owning VTI (use backtest data)
6. Monte Carlo outlook — what does the simulation project? What's the probability of loss?
7. Bull case vs Bear case — present both sides
8. One paragraph narrative: what drove this week's performance (connect news to moves, mention technicals)
9. One thing to watch next week based on news trends and economic calendar

Note any ongoing alerts (concentration, sustained fear, drift).
Keep it to 15-18 sentences.
{EDUCATOR_RULE}""",

    "interactive": f"""The user asked a question about their portfolio. They are 19 and
learning to invest.

Answer their question directly using the data, news, quant analysis, and bull/bear perspectives.
If they ask about a concept, explain it clearly with examples from their own portfolio.
If the question is about something not covered in the data, say so.
Be concise but don't skip the explanation — this is how they learn.
{EDUCATOR_RULE}""",
}


def synthesis_agent(state: AgentState) -> dict:
    """Combines all reports into a final briefing based on the mode."""
    mode = state["mode"]
    question = state.get("question", "")

    instructions = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["intraday"])

    question_block = ""
    if mode == "interactive" and question:
        question_block = f"\nUser question: {question}\n"

    prompt = f"""{instructions}
{question_block}
=== DATA REPORT ===
{state['data_report']}

=== NEWS & INTELLIGENCE REPORT ===
{state['news_report']}

=== QUANT REPORT ===
{state['quant_report']}

=== BULL CASE ===
{state['bull_report']}

=== BEAR CASE ===
{state['bear_report']}

Rules:
- Use specific numbers from the reports. Never fabricate.
- Connect news to price moves when the link is clear.
- If there are alerts, always mention them — they're important.
- If RECENT DECISION MEMORY is present, reference it to show awareness of past context.
- Never recommend buying, selling, or holding.

After your response, add a final line starting with "TAKEAWAY:" followed by
a single sentence summary of the most important insight from this briefing.
This will be stored for future context."""

    response = llm_invoke_with_retry([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    full_response = sanitize_response(response.content)

    # Extract and store takeaway for decision memory
    takeaway = ""
    if "TAKEAWAY:" in full_response:
        parts = full_response.split("TAKEAWAY:", 1)
        takeaway = parts[1].strip().split("\n")[0].strip()
        # Remove the TAKEAWAY line from the user-facing message
        full_response = parts[0].strip()

    if takeaway:
        # Get current portfolio value from data report
        portfolio_value = None
        for line in state["data_report"].split("\n"):
            if line.startswith("Total: $"):
                try:
                    portfolio_value = float(line.split("$")[1].split(" ")[0].replace(",", ""))
                except (ValueError, IndexError):
                    pass
        store_decision_memory(mode, takeaway, portfolio_value)

    # Enforce hard word cap for intraday messages via LLM summarization
    if mode == "intraday" and len(full_response.split()) > INTRADAY_WORD_LIMIT:
        log.info(f"Intraday message is {len(full_response.split())} words, summarizing to {INTRADAY_WORD_LIMIT}")
        compress_prompt = (
            f"Rewrite this market update in {INTRADAY_WORD_LIMIT} words or fewer. "
            f"Keep all alerts, numbers, and ticker names. Cut filler and explanations. "
            f"Do not add new information.\n\n{full_response}"
        )
        compressed = llm_invoke_with_retry([
            SystemMessage(content="You are a concise financial editor. Output only the rewritten text."),
            HumanMessage(content=compress_prompt),
        ])
        full_response = sanitize_response(compressed.content)

    return {"synthesis": full_response}


# --- Build Graph ---

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("data_agent", data_agent)
    graph.add_node("news_agent", news_agent)
    graph.add_node("quant_agent", quant_agent)
    graph.add_node("bull_agent", bull_agent)
    graph.add_node("bear_agent", bear_agent)
    graph.add_node("synthesis_agent", synthesis_agent)

    # Phase 1: data + news + quant in parallel
    graph.add_edge(START, "data_agent")
    graph.add_edge(START, "news_agent")
    graph.add_edge(START, "quant_agent")

    # Phase 2: bull + bear in parallel (wait for all phase 1)
    graph.add_edge("data_agent", "bull_agent")
    graph.add_edge("news_agent", "bull_agent")
    graph.add_edge("quant_agent", "bull_agent")

    graph.add_edge("data_agent", "bear_agent")
    graph.add_edge("news_agent", "bear_agent")
    graph.add_edge("quant_agent", "bear_agent")

    # Phase 3: synthesis (waits for bull + bear)
    graph.add_edge("bull_agent", "synthesis_agent")
    graph.add_edge("bear_agent", "synthesis_agent")

    graph.add_edge("synthesis_agent", END)

    return graph.compile()

workflow = build_graph()


def run_agents(mode, question=""):
    """Run the full multi-agent pipeline. Returns the synthesized response."""
    holdings = get_holdings()
    if not holdings:
        return "Portfolio is empty — no positions to analyze. Add a position via Telegram to resume updates."
    result = workflow.invoke({
        "mode": mode,
        "question": question,
        "holdings": holdings,
        "data_report": "",
        "news_report": "",
        "quant_report": "",
        "bull_report": "",
        "bear_report": "",
        "synthesis": "",
    })
    return result["synthesis"]
