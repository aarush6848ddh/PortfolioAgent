"""PDF weekly report generation with charts."""
import os
import logging
from datetime import date
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from portfolio import (
    get_holdings, get_finnhub_quote, get_prev_close,
    get_monthly_snapshots, get_total_contributions, get_total_dividends,
)

log = logging.getLogger("reports")

REPORT_DIR = os.path.expanduser("~/portfolioagent/reports")


def ensure_report_dir():
    os.makedirs(REPORT_DIR, exist_ok=True)


def generate_allocation_pie(holdings):
    """Generate allocation pie chart, return file path."""
    ensure_report_dir()
    labels = []
    sizes = []

    for h in holdings:
        quote = get_finnhub_quote(h["ticker"])
        price = quote["current"] if quote else get_prev_close(h["ticker"])
        if price:
            labels.append(h["ticker"])
            sizes.append(price * h["shares"])

    if not sizes:
        return None

    fig, ax = plt.subplots(figsize=(6, 6))
    colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f"]
    ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90,
           colors=colors[:len(labels)], textprops={"fontsize": 12})
    ax.set_title("Portfolio Allocation", fontsize=14, fontweight="bold")

    path = os.path.join(REPORT_DIR, f"allocation_{date.today()}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_pl_chart(snapshots):
    """Generate P&L history line chart, return file path."""
    ensure_report_dir()
    if not snapshots or len(snapshots) < 2:
        return None

    dates = [s["date"] for s in snapshots]
    values = [s["total_value"] for s in snapshots]
    costs = [s["total_cost"] for s in snapshots]
    daily_pl = [s["day_pl"] for s in snapshots]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [2, 1]})

    # Portfolio value vs cost basis
    ax1.plot(dates, values, label="Portfolio Value", color="#4e79a7", linewidth=2)
    ax1.plot(dates, costs, label="Cost Basis", color="#e15759", linewidth=1, linestyle="--")
    ax1.fill_between(dates, costs, values, alpha=0.15,
                     where=[v >= c for v, c in zip(values, costs)], color="green")
    ax1.fill_between(dates, costs, values, alpha=0.15,
                     where=[v < c for v, c in zip(values, costs)], color="red")
    ax1.set_title("Portfolio Value vs Cost Basis", fontsize=14, fontweight="bold")
    ax1.set_ylabel("Value ($)")
    ax1.legend()
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax1.grid(True, alpha=0.3)

    # Daily P&L bar chart
    bar_colors = ["green" if p >= 0 else "red" for p in daily_pl]
    ax2.bar(dates, daily_pl, color=bar_colors, alpha=0.7)
    ax2.set_title("Daily P&L", fontsize=12, fontweight="bold")
    ax2.set_ylabel("P&L ($)")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax2.axhline(y=0, color="black", linewidth=0.5)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(REPORT_DIR, f"pl_history_{date.today()}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_weekly_report():
    """Generate full weekly report with charts. Returns list of image paths."""
    holdings = get_holdings()
    snapshots = get_monthly_snapshots()

    paths = []

    pie_path = generate_allocation_pie(holdings)
    if pie_path:
        paths.append(pie_path)

    pl_path = generate_pl_chart(snapshots)
    if pl_path:
        paths.append(pl_path)

    return paths
