import asyncio
import json
import os
from typing import Any, Dict, List, Optional
import aiohttp  
from aiogram import Bot, Dispatcher  
from dotenv import load_dotenv  

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3600"))
STATE_FILE = os.getenv("STATE_FILE", "state.json")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")

if not GITHUB_TOKEN or not GITHUB_USERNAME:
    raise RuntimeError("Missing GITHUB_TOKEN or GITHUB_USERNAME in .env")

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"last_event_id": None}

def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

async def fetch_github_events(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/events"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}", 
        "User-Agent": "gh-telegram-notify-bot",
    }

    async with session.get(url, headers=headers, timeout=10) as resp:
        if resp.status !=200:
            text = await resp.text()
            raise RuntimeError(f"GitHub API error {resp.status}: {text}")
        return await resp.json()

def is_new_repo_event(event: Dict[str, Any]) -> bool:
    if event.get("type") != "CreateEvent":
        return False
    payload = event.get("payload")
    return payload.get("ref_type") == "repository"

def is_merge_event(event: Dict[str, Any]) -> bool:
    if event.get("type") != "PullRequestEvent":
        return False
    payload = event.get("payload") or {}
    if payload.get("action") != "closed":
        return False
    pr = payload.get("pull_request") or {}
    return bool(pr.get("merged"))

def format_repo_created(event: Dict[str, Any]) -> str:
    repo = (event.get("repo") or {}).get("name", "unknown")
    created_at = event.get("created_at", "")
    return f"🆕 Создан репозиторий: <b>{repo}</b>\n⏰ {created_at}"

def format_merged(event: Dict[str, Any]) -> str:
    payload = event.get("payload") or {}
    pr = payload.get("pull_request") or {}
    title = pr.get("title", "PR")
    number = pr.get("number")
    html_url = pr.get("html_url")
    base_repo = ((pr.get("base") or {}).get("repo") or {}).get("full_name")
    line_repo = f"<b>{base_repo}</b>" if base_repo else "<b>unknown repo</b>"
    line_num = f"#{number}" if number is not None else ""
    line_link = f"\n🔗 {html_url}" if html_url else ""
    return f"✅ Мердж PR {line_num} в {line_repo}\n📝 {title}{line_link}"


def build_messages(event: Dict[str, Any]) -> Optional[str]:
    if is_new_repo_event(event):
        return format_repo_created(event)
    if is_merge_event(event):
        return format_merged(event)
    return None

async def notify_new_events(bot: Bot) -> None:
    sate = load_state()
    last_event_id = state.get("last_event_id")

    async with aiohttp.ClientSession() as session:
        events = await fetch_github_events(session)
    
    new_events: List[Dict[str, Any]] = []