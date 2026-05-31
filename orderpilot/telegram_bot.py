"""Real Telegram integration for the FULL version — OFF by default.

This module is only imported/started when TELEGRAM_BOT_TOKEN is set. It is a
thin adapter: every Telegram update is forwarded to the exact same
`bot.handle_message()` that powers the in-browser simulator, so the demo and
the live bot share one brain. With no token set, none of this runs and the
`python-telegram-bot` dependency isn't even needed for the demo.

To enable the live bot:
    1. Create a bot with @BotFather and copy the token.
    2. `pip install "python-telegram-bot>=21"`
    3. Set TELEGRAM_BOT_TOKEN in your environment / .env
    4. `python -m orderpilot.telegram_bot`
"""
from . import bot, config, db


def _conv_id(chat_id: int) -> str:
    # Namespace Telegram chats so they never collide with simulator sessions.
    return f"tg-{chat_id}"


async def _on_message(update, context):  # pragma: no cover - needs live Telegram
    chat_id = update.effective_chat.id
    text = update.message.text or ""
    replies = bot.handle_message(_conv_id(chat_id), text, channel="telegram")
    for reply in replies:
        await context.bot.send_message(
            chat_id=chat_id, text=reply, parse_mode="Markdown"
        )


def run() -> None:  # pragma: no cover - needs live Telegram
    """Start long-polling the live Telegram bot. Requires a token."""
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. The live Telegram bot is disabled.\n"
            "The zero-config demo does not need it — run the FastAPI app instead:\n"
            "    uvicorn app:app --reload"
        )
    try:
        from telegram import Update
        from telegram.ext import (ApplicationBuilder, ContextTypes, MessageHandler,
                                   filters)
    except ImportError as exc:  # noqa: F841
        raise SystemExit(
            "python-telegram-bot is not installed. Install the full-version "
            'dependency:\n    pip install "python-telegram-bot>=21"'
        )

    db.init_db(seed=True)
    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT, _on_message))
    print("OrderPilot live Telegram bot started. Press Ctrl+C to stop.")
    application.run_polling()


if __name__ == "__main__":  # pragma: no cover
    run()
