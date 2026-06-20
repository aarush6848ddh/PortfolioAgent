"""Interactive Telegram bot — lets the user ask questions about their portfolio.
Uses the multi-agent orchestrator for every answer.
Runs as a long-polling loop (systemd service).
"""
import os
from dotenv import load_dotenv
from telegram import send_message, get_updates
from portfolio import log_run
from orchestrator import run_agents

load_dotenv()

CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def run_bot():
    print("Bot started. Listening for messages...")
    offset = None

    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1

                msg = update.get("message")
                if not msg or not msg.get("text"):
                    continue

                if str(msg["chat"]["id"]) != CHAT_ID:
                    continue

                question = msg["text"].strip()
                print(f"Q: {question}")

                try:
                    answer = run_agents("interactive", question=question)
                    log_run("interactive", question, answer, True, "user asked a question")
                    send_message(answer)
                    print(f"A: {answer[:100]}...")
                except Exception as e:
                    error_msg = f"Error processing your question: {str(e)}"
                    log_run("interactive", question, error_msg, True, f"error: {str(e)}")
                    send_message(error_msg, disclaimer=False)
                    print(f"Error: {e}")

        except KeyboardInterrupt:
            print("\nBot stopped.")
            break
        except Exception as e:
            print(f"Polling error: {e}")
            import time
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
