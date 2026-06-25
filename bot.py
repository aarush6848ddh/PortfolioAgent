"""Interactive Telegram bot — python-telegram-bot async implementation.

Features:
  - Natural language trade logging (text or brokerage screenshot)
  - Inline keyboard confirmation for trades
  - Quick-access inline keyboard (snapshot, movers, allocation, P&L)
  - Portfolio Q&A via multi-agent orchestrator
  - Target allocation setting
  - Health check endpoint
  - Auto-reconnect, proper error handling
"""
import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

from portfolio import (
    log_run, get_holdings, get_finnhub_quote, get_prev_close,
    set_target_allocation, get_target_allocations,
)
from orchestrator import run_agents
from trade_parser import parse_trade, parse_trade_image
from portfolioagent import buy, sell
from health import start_health_check

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
MAX_MSG_LEN = 4096


# --- Helpers ---

async def send_chunked(text, context, chat_id=CHAT_ID):
    """Send a message, splitting into chunks if needed. Markdown with fallback."""
    chunks = [text[i:i + MAX_MSG_LEN] for i in range(0, len(text), MAX_MSG_LEN)]
    for chunk in chunks:
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=chunk, parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=chunk)


def format_trade_confirmation(trade):
    action = trade["action"].upper()
    ticker = trade["ticker"]
    shares = trade["shares"]
    parts = [f"\U0001f4dd {action} {shares} {ticker}"]
    if trade.get("price"):
        parts.append(f"@ ${trade['price']}")
    if trade.get("time"):
        parts.append(f"at {trade['time']} ET")
    return " ".join(parts)


def execute_trade(trade):
    action = trade["action"]
    ticker = trade["ticker"]
    shares = trade["shares"]
    price = trade.get("price")

    if action == "buy":
        if not price:
            return "\u274c Need a price to log a buy. Try again with the cost basis."
        buy(ticker, str(shares), str(price))
        return f"\u2705 Bought {shares} shares of {ticker} at ${price}"
    elif action == "sell":
        sell(ticker, str(shares), str(price) if price else None)
        msg = f"\u2705 Sold {shares} shares of {ticker}"
        if price:
            msg += f" at ${price}"
        return msg
    return "\u274c Unknown action."


def trade_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 Confirm", callback_data="trade_confirm"),
            InlineKeyboardButton("\u274c Cancel", callback_data="trade_cancel"),
        ]
    ])


def menu_keyboard():
    """Quick-access menu keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f4ca Snapshot", callback_data="menu_snapshot"),
            InlineKeyboardButton("\U0001f4c8 Movers", callback_data="menu_movers"),
        ],
        [
            InlineKeyboardButton("\U0001f3af Allocation", callback_data="menu_allocation"),
            InlineKeyboardButton("\U0001f4b0 P&L", callback_data="menu_pl"),
        ],
    ])


# --- Quick Data Helpers (no LLM) ---

def get_snapshot_text():
    """Quick portfolio snapshot — no LLM call."""
    holdings = get_holdings()
    lines = ["\U0001f4ca *Portfolio Snapshot*\n"]
    total_value = 0
    total_cost = 0
    for h in holdings:
        quote = get_finnhub_quote(h["ticker"])
        price = quote["current"] if quote else get_prev_close(h["ticker"])
        if not price:
            continue
        value = price * h["shares"]
        cost = h["cost_basis"] * h["shares"]
        total_value += value
        total_cost += cost
        pl = value - cost
        pct = (price - h["cost_basis"]) / h["cost_basis"] * 100
        day_change = f"{quote['change_pct']:+.2f}%" if quote else "N/A"
        lines.append(f"*{h['ticker']}*: ${price:.2f} ({day_change})")
        lines.append(f"  {h['shares']} shares | Value: ${value:.2f} | P&L: ${pl:+.2f} ({pct:+.1f}%)")
    lines.append(f"\n*Total*: ${total_value:.2f} | P&L: ${total_value - total_cost:+.2f}")
    return "\n".join(lines)


def get_movers_text():
    """Today's movers sorted by absolute change."""
    holdings = get_holdings()
    movers = []
    for h in holdings:
        quote = get_finnhub_quote(h["ticker"])
        if quote:
            day_pl = (quote["current"] - quote["prev_close"]) * h["shares"]
            movers.append({"ticker": h["ticker"], "change_pct": quote["change_pct"], "day_pl": day_pl})
    movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    lines = ["\U0001f4c8 *Today's Movers*\n"]
    for m in movers:
        emoji = "\U0001f7e2" if m["change_pct"] >= 0 else "\U0001f534"
        lines.append(f"{emoji} *{m['ticker']}*: {m['change_pct']:+.2f}% (${m['day_pl']:+.2f})")
    return "\n".join(lines)


def get_allocation_text():
    """Current allocation breakdown."""
    holdings = get_holdings()
    total_value = 0
    items = []
    for h in holdings:
        quote = get_finnhub_quote(h["ticker"])
        price = quote["current"] if quote else get_prev_close(h["ticker"])
        if price:
            value = price * h["shares"]
            total_value += value
            items.append({"ticker": h["ticker"], "value": value})
    lines = ["\U0001f3af *Allocation*\n"]
    targets = get_target_allocations()
    for item in items:
        pct = (item["value"] / total_value * 100) if total_value > 0 else 0
        target_str = ""
        if targets.get(item["ticker"]):
            target = targets[item["ticker"]]
            drift = pct - target
            target_str = f" (target: {target:.0f}%, drift: {drift:+.1f}pp)"
        lines.append(f"*{item['ticker']}*: {pct:.1f}% (${item['value']:.2f}){target_str}")
    lines.append(f"\n*Total*: ${total_value:.2f}")
    return "\n".join(lines)


def get_pl_text():
    """P&L summary."""
    holdings = get_holdings()
    lines = ["\U0001f4b0 *P&L Summary*\n"]
    total_value = 0
    total_cost = 0
    total_day_pl = 0
    for h in holdings:
        quote = get_finnhub_quote(h["ticker"])
        price = quote["current"] if quote else get_prev_close(h["ticker"])
        if not price:
            continue
        value = price * h["shares"]
        cost = h["cost_basis"] * h["shares"]
        total_value += value
        total_cost += cost
        pl = value - cost
        pct = (price - h["cost_basis"]) / h["cost_basis"] * 100
        if quote:
            day_pl = (quote["current"] - quote["prev_close"]) * h["shares"]
            total_day_pl += day_pl
            lines.append(f"*{h['ticker']}*: Total ${pl:+.2f} ({pct:+.1f}%) | Today ${day_pl:+.2f}")
        else:
            lines.append(f"*{h['ticker']}*: Total ${pl:+.2f} ({pct:+.1f}%)")
    lines.append(f"\n*Total P&L*: ${total_value - total_cost:+.2f}")
    lines.append(f"*Today*: ${total_day_pl:+.2f}")
    return "\n".join(lines)


# --- Handlers ---

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quick-access menu."""
    if update.effective_chat.id != CHAT_ID:
        return
    await update.message.reply_text("What do you want to see?", reply_markup=menu_keyboard())


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quick-access menu button presses."""
    query = update.callback_query
    await query.answer()

    action = query.data
    try:
        if action == "menu_snapshot":
            text = get_snapshot_text()
        elif action == "menu_movers":
            text = get_movers_text()
        elif action == "menu_allocation":
            text = get_allocation_text()
        elif action == "menu_pl":
            text = get_pl_text()
        else:
            text = "Unknown action."

        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await query.edit_message_text(text)
    except Exception as e:
        log.error(f"Menu action error: {e}", exc_info=True)
        await query.edit_message_text(f"Error: {e}")


async def handle_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set target allocation: /target SOXX 40 VTI 60"""
    if update.effective_chat.id != CHAT_ID:
        return
    args = context.args
    if not args or len(args) % 2 != 0:
        await update.message.reply_text("Usage: /target SOXX 40 VTI 60")
        return
    pairs = []
    for i in range(0, len(args), 2):
        ticker = args[i].upper()
        try:
            pct = float(args[i + 1])
        except ValueError:
            await update.message.reply_text(f"Invalid percentage: {args[i + 1]}")
            return
        pairs.append((ticker, pct))
    total = sum(p[1] for p in pairs)
    if abs(total - 100) > 0.1:
        await update.message.reply_text(f"Percentages must add to 100 (got {total})")
        return
    for ticker, pct in pairs:
        set_target_allocation(ticker, pct)
    summary = ", ".join(f"{t}: {p}%" for t, p in pairs)
    await update.message.reply_text(f"\U0001f3af Target allocation set: {summary}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    photo = update.message.photo[-1]
    file = await photo.get_file()
    photo_url = file.file_path
    try:
        trade = parse_trade_image(photo_url)
    except Exception as e:
        log.error(f"Image parse error: {e}", exc_info=True)
        await update.message.reply_text(f"Error reading image: {e}")
        return
    if trade:
        context.user_data["pending_trade"] = trade
        text = format_trade_confirmation(trade)
        await update.message.reply_text(text, reply_markup=trade_keyboard())
    else:
        await update.message.reply_text(
            "\U0001f937 Couldn't parse a trade from that image. Try typing it out."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    text = update.message.text.strip()
    log.info(f"Q: {text}")

    try:
        trade = parse_trade(text)
    except Exception as e:
        log.error(f"Trade parse error: {e}", exc_info=True)
        trade = None

    if trade:
        context.user_data["pending_trade"] = trade
        confirm_text = format_trade_confirmation(trade)
        await update.message.reply_text(confirm_text, reply_markup=trade_keyboard())
        return

    try:
        answer = run_agents("interactive", question=text)
        log_run("interactive", text, answer, True, "user asked a question")
        await send_chunked(answer, context, chat_id=update.effective_chat.id)
        log.info(f"A: {answer[:100]}...")
    except Exception as e:
        error_msg = f"Error processing your question: {str(e)}"
        log_run("interactive", text, error_msg, True, f"error: {str(e)}")
        await update.message.reply_text(error_msg)
        log.error(f"Error: {e}", exc_info=True)


async def handle_trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trade = context.user_data.pop("pending_trade", None)
    if not trade:
        await query.edit_message_text("\u23f0 Trade expired. Send it again.")
        return
    if query.data == "trade_confirm":
        result = execute_trade(trade)
        log_run("trade", str(trade), result, True, "trade confirmed")
        await query.edit_message_text(result)
    elif query.data == "trade_cancel":
        await query.edit_message_text("\u274c Trade cancelled.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Unhandled exception:", exc_info=context.error)


# --- Main ---

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    start_health_check()

    app = Application.builder().token(token).build()

    # Command handlers
    app.add_handler(CommandHandler("menu", handle_menu))
    app.add_handler(CommandHandler("target", handle_target))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(handle_trade_callback, pattern="^trade_"))
    app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern="^menu_"))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    log.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
