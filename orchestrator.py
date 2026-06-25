"""Multi-agent orchestrator using LangGraph.

Four specialist agents run in parallel, then a synthesis agent combines their reports:

  [START] ──┬── data_agent ───┐
             ├── news_agent ───┼── synthesis_agent ── [END]
             └── quant_agent ──┘
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
    get_yesterday_closes, get_total_contributions, ET,
)
from quant import get_quant_summary, format_quant_for_prompt
from news import get_full_intel
from sentiment import (
    get_fear_greed, format_fear_greed,
    store_fear_greed, check_sustained_fear, get_avg_fear_greed,
)
from config import (
    CONCENTRATION_BASE_PCT, CONCENTRATION_STEP_PCT,
    BIG_MOVE_PCT, DRAWDOWN_ALERT_PCT,
    INTRADAY_WORD_LIMIT, MORNING_WORD_LIMIT,
)

load_dotenv()

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.3)

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
    synthesis: Annotated[str, merge_str]

# --- Agent Nodes ---

def data_agent(state: AgentState) -> dict:
    """Gathers portfolio snapshot — prices, P&L, streaks, allocation,
    performance attribution, and threshold alerts."""
    holdings = state["holdings"]
    mode = state["mode"]

    lines = []
    total_value = 0.0
    total_cost = 0.0
    total_day_pl = 0.0
    attribution = []
    alerts = []
    big_move_tickers = []

    for h in holdings:
        quote = get_finnhub_quote(h["ticker"])
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

        streak_str = f"{abs(streak)}-day {'up' if streak > 0 else 'down'} streak" if streak != 0 else "no streak"

        parts = [
            f"{h['ticker']}: {h['shares']} shares @ ${h['cost_basis']:.2f}",
            f"now ${price:.2f}",
            f"P&L: ${pl:.2f} ({pl_pct:+.1f}%)",
            streak_str,
        ]

        if quote:
            parts.append(f"today: {quote['change_pct']:+.2f}%")
            parts.append(f"range: ${quote['low']:.2f}-${quote['high']:.2f}")
            day_pl = (quote["current"] - quote["prev_close"]) * h["shares"]
            total_day_pl += day_pl
            attribution.append({"ticker": h["ticker"], "day_pl": day_pl})

            # Big intraday move
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
    for h in holdings:
        q = get_finnhub_quote(h["ticker"])
        p = q["current"] if q else get_prev_close(h["ticker"])
        if p and total_value > 0:
            weight = (p * h["shares"]) / total_value * 100
            alloc.append(f"{h['ticker']}: {weight:.1f}%")

            if weight > CONCENTRATION_BASE_PCT:
                current_step = int(weight // CONCENTRATION_STEP_PCT) * CONCENTRATION_STEP_PCT
                last_step = get_alert_threshold(f"concentration_{h['ticker']}")
                if last_step is None or current_step > float(last_step):
                    alerts.append(f"CONCENTRATION: {h['ticker']} is {weight:.0f}% of your portfolio")
                    set_alert_threshold(f"concentration_{h['ticker']}", current_step)
            else:
                # Reset when below base threshold so it fires again if it crosses back
                if get_alert_threshold(f"concentration_{h['ticker']}"):
                    set_alert_threshold(f"concentration_{h['ticker']}", 0)

    lines.append(f"Allocation: {', '.join(alloc)}")
    lines.append(f"Total: ${total_value:.2f} | Cost: ${total_cost:.2f} | P&L: ${total_value - total_cost:+.2f} | Day P&L: ${total_day_pl:+.2f}")

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

    # Flag which tickers had big moves (for synthesis to decide on beta explanation)
    if big_move_tickers:
        lines.append(f"\nBIG_MOVE_TICKERS: {', '.join(big_move_tickers)}")
    else:
        lines.append(f"\nBIG_MOVE_TICKERS: NONE")

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

    # Morning: yesterday's close
    if mode == "morning":
        yesterday = get_yesterday_closes([h["ticker"] for h in holdings])
        if yesterday:
            lines.append("\n=== YESTERDAY'S CLOSE ===")
            for ticker, data in yesterday.items():
                lines.append(f"  {ticker}: ${data['price']:.2f} ({data['date']})")

        # Monday: last week's P&L
        if datetime.now(ET).weekday() == 0:
            last_week = get_last_week_snapshots()
            if last_week:
                week_pl = sum(s["day_pl"] for s in last_week)
                lines.append(f"\n=== LAST WEEK P&L ===")
                lines.append(f"  Total: ${week_pl:+.2f} over {len(last_week)} trading days")

    # Daily: store snapshot
    if mode == "daily":
        fg_score = fg["score"] if fg else None
        store_daily_snapshot(total_value, total_cost, total_day_pl, fg_score)

    # Weekly: aggregate stats from daily snapshots + contributions
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
        if contributions > 0:
            gains = total_value - contributions
            lines.append(f"\n=== YOUR MONEY vs MARKET GAINS ===")
            lines.append(f"  Your money (total deposited): ${contributions:.2f}")
            lines.append(f"  Market gains: ${gains:+.2f}")

    return {"data_report": "\n".join(lines)}


def news_agent(state: AgentState) -> dict:
    """Fetches full market intelligence then uses LLM to synthesize."""
    holdings = state["holdings"]
    intel_text = get_full_intel(holdings)

    tickers = [h["ticker"] for h in holdings]
    prompt = f"""You are a market intelligence analyst briefing a beginner investor who is
learning how markets work. The portfolio holds: {', '.join(tickers)}.

Analyze this data and produce a concise intelligence report covering:
1. News sentiment — what's the overall tone? Any headline that could move prices?
2. Positioning context — where is each holding relative to its 52-week range?
   Is anything near a high or low? Explain why this matters.
3. Insider signals — if insider data exists, explain what MSPR means and what
   the current reading tells us.
4. Earnings risk — are any companies reporting soon? Explain why earnings matter.
5. Relative performance — how are the holdings doing vs the S&P 500?

When you mention a concept (52-week high, relative performance, etc.), briefly
explain what it means in plain English. Be concise but educational.

End your report with this exact line format:
OVERNIGHT_SENTIMENT: X/10
(1 = very bearish, 5 = neutral, 10 = very bullish, based on overall news tone)

{intel_text}"""

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return {"news_report": sanitize_response(response.content)}


def quant_agent(state: AgentState) -> dict:
    """Runs quant analysis, then uses LLM to interpret the numbers."""
    holdings = state["holdings"]
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

State the numbers, then give a brief plain-English interpretation of each.
Keep it factual and concise. Do NOT give investment advice.

{quant_text}"""

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return {"quant_report": sanitize_response(response.content)}


EDUCATOR_RULE = """
IMPORTANT: The user is 19 and learning to invest. When you mention any financial
concept, briefly explain it in plain English. For example:
- "Sharpe ratio of 2.05 (this measures return per unit of risk — above 1 is good,
  above 2 is excellent)"
Don't be condescending — be the smart friend who explains things clearly.
"""

MODE_INSTRUCTIONS = {
    "morning": f"""It's morning, before market open. Synthesize a concise morning briefing.

Structure:
1. Start with yesterday's close for each holding (use the YESTERDAY'S CLOSE data)
2. State the Fear & Greed reading and the overnight news sentiment score
3. One sentence outlook for the day based on beta exposure, Fear & Greed, and news
4. Surface any alerts
5. If LAST WEEK P&L data is present (Monday), include it as a single line

HARD LIMIT: {MORNING_WORD_LIMIT} words maximum. Be direct.
{EDUCATOR_RULE}""",

    "intraday": f"""It's during market hours. Synthesize an intraday update.

Rules:
- Put any ALERTS at the very top, clearly labeled
- If there are no alerts AND nothing notable is happening, respond with exactly: SILENT
- Do NOT explain what beta means UNLESS the BIG_MOVE_TICKERS field lists a ticker
  (only then, briefly note its beta to explain why the move is amplified)
- Do NOT mention 52-week high/low unless a holding actually broke to a new 52-week
  high TODAY (current price >= 52-week high in the data)
- Do NOT repeat Sharpe ratio, Sortino, drawdown, backtest, or correlation data
- Do NOT include a disclaimer
- Focus on: what moved, by how much, why (connect to news if clear)

HARD LIMIT: {INTRADAY_WORD_LIMIT} words maximum. Shorter is better.
{EDUCATOR_RULE}""",

    "daily": f"""It's end of day. Synthesize a daily summary:
- Start with how much the portfolio made or lost today (total and per-holding attribution)
- Who was the biggest mover and why (connect to news)
- Include the Fear & Greed reading
- Note any alerts
- Keep it to 6-8 sentences.
{EDUCATOR_RULE}""",

    "weekly": f"""It's the weekend. Synthesize a weekly digest.

Required sections:
1. Total week P&L (from WEEKLY STATS)
2. Best day and worst day (from WEEKLY STATS)
3. Average Fear & Greed for the week
4. YOUR MONEY vs MARKET GAINS — show how much was deposited vs how much the market added
5. How the portfolio stacks up against just owning VTI (use backtest data)
6. One paragraph narrative: what drove this week's performance (connect news to moves)
7. One thing to watch next week based on news trends

Note any ongoing alerts (concentration, sustained fear).
Keep it to 12-15 sentences.
{EDUCATOR_RULE}""",

    "interactive": f"""The user asked a question about their portfolio. They are 19 and
learning to invest.

Answer their question directly using the data, news, and quant analysis provided.
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

Rules:
- Use specific numbers from the reports. Never fabricate.
- Connect news to price moves when the link is clear.
- If there are alerts, always mention them — they're important.
- Never recommend buying, selling, or holding."""

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return {"synthesis": sanitize_response(response.content)}


# --- Build Graph ---

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("data_agent", data_agent)
    graph.add_node("news_agent", news_agent)
    graph.add_node("quant_agent", quant_agent)
    graph.add_node("synthesis_agent", synthesis_agent)

    graph.add_edge(START, "data_agent")
    graph.add_edge(START, "news_agent")
    graph.add_edge(START, "quant_agent")

    graph.add_edge("data_agent", "synthesis_agent")
    graph.add_edge("news_agent", "synthesis_agent")
    graph.add_edge("quant_agent", "synthesis_agent")

    graph.add_edge("synthesis_agent", END)

    return graph.compile()

workflow = build_graph()


def run_agents(mode, question=""):
    """Run the full multi-agent pipeline. Returns the synthesized response."""
    holdings = get_holdings()
    result = workflow.invoke({
        "mode": mode,
        "question": question,
        "holdings": holdings,
        "data_report": "",
        "news_report": "",
        "quant_report": "",
        "synthesis": "",
    })
    return result["synthesis"]
