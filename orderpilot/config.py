"""Configuration for OrderPilot.

Everything here has a safe default so the demo runs with ZERO config. The only
setting that changes behaviour is TELEGRAM_BOT_TOKEN: leave it empty (the
default) and the live Telegram bot stays OFF — the app runs purely as the
in-browser simulator. Set it and the full version connects to Telegram.
"""
import os
from pathlib import Path

# Load a local .env if python-dotenv is installed (optional convenience only).
try:  # pragma: no cover - trivial
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# The fictional shop the bot represents. Deliberately an "Acme"-style name so
# nobody could mistake the demo for a real business.
SHOP_NAME = os.getenv("ORDERPILOT_SHOP_NAME", "Acme Coffee Co.")
SHOP_TAGLINE = "fictional demo shop"
CURRENCY = "$"

# SQLite location. The demo seeds a throwaway file under the project.
DB_PATH = os.getenv("ORDERPILOT_DB_PATH", str(BASE_DIR / "orderpilot_demo.db"))

# Live Telegram bot is OFF unless a token is provided. The demo never needs it.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
LIVE_TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)

# Shown on every page so the demo can never be mistaken for a live deployment.
DEMO_BANNER = "Demo — simulated bot, not connected to Telegram. All data is fictional."
