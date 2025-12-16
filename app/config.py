import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "").encode()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not GITHUB_WEBHOOK_SECRET:
    raise RuntimeError("Missing required environment variables")
