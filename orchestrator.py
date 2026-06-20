"""Multi-agent orchestrator using LangGraph.

Four specialist agents run in parallel, then a synthesis agent combines their reports:

  [START] ──┬── data_agent ───┐
             ├── news_agent ───┼── synthesis_agent ── [END]
             └── quant_agent ──┘

Each agent has a narrow scope and produces a structured report.
The synthesis agent combines all reports with mode-specific instructions.
"""
import os
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv

from portfolio import (
    get_holdings, get_finnhub_quote, get_prev_close, get_streak,
    store_daily_close, get_conn, SYSTEM_PROMPT, sanitize_response
)
from quant import get_quant_summary, format_quant_for_prompt
from news import get_full_intel
from sentiment import get_fear_greed, format_fear_greed

load_dotenv()

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)

# --- State ---

def merge_str(existing: str, new: str) -> str:
    """Reducer: later value overwrites."""
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
    performance attribution, and threshold alerts. No LLM call."""
    holdings = state["holdings"]
    mode = state["mode"]

    lines = []
    total_value = 0.0
    total_cost = 0.0
    total_day_pl = 0.0
    attribution = []  # tracks each holding's contribution to daily P&L
    alerts = []       # threshold-based warnings

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

            # --- Threshold alerts ---
            # Big intraday move
            if abs(quote["change_pct"]) >= 3.0:
                alerts.append(f"BIG MOVE: {h['ticker']} is {'up' if quote['change_pct'] > 0 else 'down'} {abs(quote['change_pct']):.1f}% today")

            if mode == "daily":
                store_daily_close(h["ticker"], price)

        lines.append(" | ".join(parts))

    # Store SPY close (daily mode)
    if mode == "daily":
        spy_quote = get_finnhub_quote("SPY")
        if spy_quote:
            store_daily_close("SPY", spy_quote["current"])

    # Allocation + concentration check
    alloc = []
    for h in holdings:
        q = get_finnhub_quote(h["ticker"])
        p = q["current"] if q else get_prev_close(h["ticker"])
        if p and total_value > 0:
            weight = (p * h["shares"]) / total_value * 100
            alloc.append(f"{h['ticker']}: {weight:.1f}%")
            if weight > 50:
                alerts.append(f"CONCENTRATION: {h['ticker']} is {weight:.0f}% of your portfolio — that's a lot of eggs in one basket")

    lines.append(f"Allocation: {', '.join(alloc)}")
    lines.append(f"Total: ${total_value:.2f} | Cost: ${total_cost:.2f} | P&L: ${total_value - total_cost:+.2f} | Day P&L: ${total_day_pl:+.2f}")

    # Drawdown from peak (total portfolio)
    if total_cost > 0:
        portfolio_return = (total_value - total_cost) / total_cost * 100
        if portfolio_return < -5:
            alerts.append(f"DRAWDOWN: portfolio is down {portfolio_return:.1f}% from your total cost basis")

    # Performance attribution
    if attribution:
        attribution.sort(key=lambda x: abs(x["day_pl"]), reverse=True)
        attr_lines = [f"  {a['ticker']}: ${a['day_pl']:+.2f}" for a in attribution]
        lines.append(f"\nDay's P&L breakdown (who moved your money):")
        lines.extend(attr_lines)

    # Threshold alerts
    if alerts:
        lines.append(f"\n=== ALERTS ===")
        for a in alerts:
            lines.append(f"  ! {a}")

    # Fear & Greed Index
    fg = get_fear_greed()
    lines.append(f"\n{format_fear_greed(fg)}")

    return {"data_report": "\n".join(lines)}


def news_agent(state: AgentState) -> dict:
    """Fetches full market intelligence — news, insider activity, fundamentals,
    earnings, analyst recommendations — then uses LLM to synthesize."""
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

{intel_text}"""

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    return {"news_report": sanitize_response(response.content)}


def quant_agent(state: AgentState) -> dict:
    """Runs quant analysis, then uses LLM to interpret the numbers in
    a beginner-friendly way."""
    holdings = state["holdings"]
    summary = get_quant_summary(holdings)
    quant_text = format_quant_for_prompt(summary)

    prompt = f"""You are a quantitative analyst explaining portfolio metrics to someone
who is 19 and learning to invest. They're smart but new to finance.

Interpret these metrics and explain what each one means in plain English:

1. Beta — what does it mean that SOXX has a beta of ~2.3? Use a simple analogy.
2. Correlation — VTI and SCHG are 0.94 correlated. Explain why this matters
   for diversification in a way that clicks.
3. Sharpe/Sortino — are these good? What do they actually measure?
4. Drawdown — what was the worst drop, and how long did recovery take?
   Why should a beginner care about this?
5. Backtest — is the portfolio beating a simple VTI-only approach?
   Is the extra complexity worth it?

State the numbers, then explain what they mean in real terms.
Keep it conversational, not textbook. Do NOT give investment advice.

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
- "VTI/SCHG correlation is 0.94 (they move almost identically, so owning both
  doesn't add much diversification)"
Don't be condescending — be the smart friend who explains things clearly.
"""

MODE_INSTRUCTIONS = {
    "morning": f"""It's morning, before market open. Synthesize a concise morning briefing:
- Start with the Fear & Greed reading and what it means for today's market mood
- What happened yesterday — who moved, by how much, and why (connect to news)
- Surface the most important quant insight and explain what it means practically
- Note any alerts or threshold warnings
- What to pay attention to today
- Keep it to 8-10 sentences. Be direct but educational.
{EDUCATOR_RULE}""",

    "intraday": f"""It's during market hours. Synthesize an intraday alert:
- Only flag things that genuinely matter: 3%+ moves, alerts, news-driven moves
- If there are threshold alerts, always include them
- If the news explains a move, connect them explicitly
- If nothing notable is happening AND there are no alerts, respond with exactly: SILENT
- Keep it to 3-5 sentences if not SILENT.
{EDUCATOR_RULE}""",

    "daily": f"""It's end of day. Synthesize a daily summary:
- Start with how much the portfolio made or lost today (total and per-holding attribution)
- Who was the biggest mover and why (connect to news)
- Include the Fear & Greed reading
- Highlight one quant concept and explain what it means for the portfolio
- Note any alerts
- Keep it to 7-9 sentences.
{EDUCATOR_RULE}""",

    "weekly": f"""It's the weekend. Synthesize a weekly digest:
- Best and worst performer this week and why
- Portfolio-level return for the week
- How the portfolio stacks up against just owning VTI (use the backtest data)
- Key quant lesson of the week — pick one concept and explain it well
- One thing to watch next week based on news trends
- Note any ongoing alerts (concentration, drawdown)
- Keep it to 10-12 sentences.
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
- Use quant data to add depth, not just repeat it.
- Include the P&L attribution (who moved your money today) when relevant.
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
