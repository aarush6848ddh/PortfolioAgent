"""Interactive Telegram bot — python-telegram-bot async implementation.

Features:
  - Natural language trade logging (text or brokerage screenshot)
  - Inline keyboard confirmation for trades
  - Portfolio Q&A via multi-agent orchestrator
  - Auto-reconnect, proper error handling
"""
import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

from portfolio import log_run
from orchestrator import run_agents
from trade_parser import parse_trade, parse_trade_image
from portfolioagent import buy, sell

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
DISCLAIMER = "\n\n---\nData analysis only — not financial advice."
MAX_MSG_LEN = 4096


# --- Helpers ---

async def send_chunked(text, context, chat_id=CHAT_ID, disclaimer=True):
    """Send a message, splitting into chunks if needed. Markdown with fallback."""
    if disclaimer:
        text += DISCLAIMER
    chunks = [text[i:i + MAX_MSG_LEN] for i in range(0, len(text), MAX_MSG_LEN)]
    for chunk in chunks:
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=chunk, parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=chunk)


def format_trade_confirmation(trade):
    """Format a parsed trade for display."""
    action = trade["action"].upper()
    ticker = trade["ticker"]
    shares = trade["shares"]
    parts = [f"📝 {action} {shares} {ticker}"]
    if trade.get("price"):
        parts.append(f"@ ${trade['price']}")
    if trade.get("time"):
        parts.append(f"at {trade['time']} ET")
    return " ".join(parts)


def execute_trade(trade):
    """Execute a confirmed trade and return a status message."""
    action = trade["action"]
    ticker = trade["ticker"]
    shares = trade["shares"]
    price = trade.get("price")

    if action == "buy":
        if not price:
            return "❌ Need a price to log a buy. Try again with the cost basis."
        buy(ticker, str(shares), str(price))
        return f"✅ Bought {shares} shares of {ticker} at ${price}"
    elif action == "sell":
        sell(ticker, str(shares), str(price) if price else None)
        msg = f"✅ Sold {shares} shares of {ticker}"
        if price:
            msg += f" at ${price}"
        return msg
    return "❌ Unknown action."


def trade_keyboard():
    """Inline keyboard for trade confirmation."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data="trade_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="trade_cancel"),
        ]
    ])


# --- Handlers ---

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle brokerage screenshot uploads."""
    if update.effective_chat.id != CHAT_ID:
        return

    photo = update.message.photo[-1]  # largest size
    file = await photo.get_file()
    photo_url = file.file_path  # python-telegram-bot gives full URL

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
            "🤷 Couldn't parse a trade from that image. Try typing it out."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages — route to trade parser or orchestrator."""
    if update.effective_chat.id != CHAT_ID:
        return

    text = update.message.text.strip()
    log.info(f"Q: {text}")

    # Try to parse as a trade
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

    # Not a trade — send to the orchestrator
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
    """Handle inline keyboard button presses for trade confirmation."""
    query = update.callback_query
    await query.answer()

    trade = context.user_data.pop("pending_trade", None)
    if not trade:
        await query.edit_message_text("⏰ Trade expired. Send it again.")
        return

    if query.data == "trade_confirm":
        result = execute_trade(trade)
        log_run("trade", str(trade), result, True, "trade confirmed")
        await query.edit_message_text(result)
    elif query.data == "trade_cancel":
        await query.edit_message_text("❌ Trade cancelled.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler."""
    log.error("Unhandled exception:", exc_info=context.error)


# --- Main ---

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()

    # Register handlers (order matters — first match wins)
    app.add_handler(CallbackQueryHandler(handle_trade_callback, pattern="^trade_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    log.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
