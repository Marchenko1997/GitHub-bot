import os
import hmac
import hashlib
import json
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Header, HTTPException
import uvicorn
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # токен твоего Telegram бота
TELEGRAM_CHAT_ID = int(
    os.getenv("TELEGRAM_CHAT_ID", "0")
)  # ID чата, куда слать уведомления
GITHUB_WEBHOOK_SECRET = os.getenv(
    "GITHUB_WEBHOOK_SECRET", ""
).encode()  # секрет для подписи GitHub webhook

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not GITHUB_WEBHOOK_SECRET:
    raise RuntimeError(
        "Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / GITHUB_WEBHOOK_SECRET in .env"
    )

bot = Bot(token=TELEGRAM_BOT_TOKEN)

app = FastAPI()

# ============================================================
# ЛОГГЕР — просто термокоды для красивых цветов
# ============================================================


def log_info(msg: str) -> None:
    print(f"\033[92m[INFO]\033[0m {msg}")


def log_warn(msg: str) -> None:
    print(f"\033[93m[WARN]\033[0m {msg}")


def log_error(msg: str) -> None:
    print(f"\033[91m[ERROR]\033[0m {msg}")


def format_push(payload: Dict[str, Any]) -> str:
    repo = payload.get("repository", {}).get("full_name", "unknown")
    branch_ref = payload.get("ref", "")
    branch = branch_ref.split("/")[-1] if branch_ref else "unknown"
    commits = payload.get("commits", [])[:3]
