import asyncio
import json
import os
from typing import Any, Dict, List, Optional
import aiohttp
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#                     ЛОГГЕР
# ============================================================


def log_info(message: str) -> None:
    print(f"\033[92m[INFO]\033[0m {message}")


def log_warn(message: str) -> None:
    print(f"\033[93m[WARN]\033[0m {message}")


def log_error(message: str) -> None:
    print(f"\033[91m[ERROR]\033[0m {message}")


# ============================================================
#                     .ENV
# ============================================================

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

# ============================================================
#                     STATE
# ============================================================


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"last_event_id": None}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        log_warn("State file corrupted — resetting.")
        return {"last_event_id": None}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================
#                     GITHUB API
# ============================================================


async def fetch_github_events(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/events"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}",
        "User-Agent": "gh-telegram-notify-bot",
    }

    async with session.get(url, headers=headers, timeout=10) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"GitHub API error {resp.status}: {text}")
        return await resp.json()


# ============================================================
#                  EVENT FILTERS
# ============================================================


def is_new_repo_event(event: Dict[str, Any]) -> bool:
    return (
        event.get("type") == "CreateEvent"
        and (event.get("payload") or {}).get("ref_type") == "repository"
    )


def is_merge_event(event: Dict[str, Any]) -> bool:
    if event.get("type") != "PullRequestEvent":
        return False
    payload = event.get("payload") or {}
    if payload.get("action") != "closed":
        return False
    pr = payload.get("pull_request") or {}
    return bool(pr.get("merged"))


# ⭐ ADD: PushEvent — коммиты
def is_push_event(event: Dict[str, Any]) -> bool:
    return event.get("type") == "PushEvent"


# ============================================================
#                     FORMATTERS
# ============================================================


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


# ⭐ ADD: формат пуш-ивента
def format_push(event: Dict[str, Any]) -> str:
    repo = (event.get("repo") or {}).get("name", "unknown")
    payload = event.get("payload") or {}
    commits = payload.get("commits", [])

    if not commits:
        return f"📌 Новый push в <b>{repo}</b> (без сообщений коммитов)"

    commit_messages = "\n".join(f"- {c.get('message', '').strip()}" for c in commits)

    return f"📌 Новый push в <b>{repo}</b>:\n{commit_messages}"


# ============================================================
#                 MESSAGE BUILDER
# ============================================================


def build_messages(event: Dict[str, Any]) -> Optional[str]:
    if is_new_repo_event(event):
        return format_repo_created(event)

    if is_merge_event(event):
        return format_merged(event)

    # ⭐ PUSH EVENT — добавлено
    if is_push_event(event):
        return format_push(event)

    return None


# ============================================================
#                MAIN GITHUB CHECKER
# ============================================================


async def notify_new_events(bot: Bot) -> None:
    log_info("Checking GitHub for new events...")

    state = load_state()
    last_event_id = state.get("last_event_id")

    async with aiohttp.ClientSession() as session:
        events = await fetch_github_events(session)

    new_events: List[Dict[str, Any]] = []

    for e in events:
        if last_event_id and e.get("id") == last_event_id:
            break
        new_events.append(e)

    if not new_events:
        log_info("No new events.")
        return

    log_info(f"Found {len(new_events)} new events!")

    new_events.reverse()

    for e in new_events:
        msg = build_messages(e)
        if msg:
            log_info(f"Sending event: {e.get('type')}")
            await bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID),
                text=msg,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

    state["last_event_id"] = events[0].get("id")
    save_state(state)
    log_info("State updated.")


# ============================================================
#                   POLLER LOOP
# ============================================================


async def poller(bot: Bot) -> None:
    log_info("Initializing poller...")

    state = load_state()

    if not state.get("last_event_id"):
        async with aiohttp.ClientSession() as session:
            events = await fetch_github_events(session)
        if events:
            state["last_event_id"] = events[0].get("id")
            save_state(state)
            log_info("Initial state created.")

    while True:
        try:
            await notify_new_events(bot)
        except Exception as e:
            log_error(f"[poller error] {e}")

        await asyncio.sleep(POLL_INTERVAL)


# ============================================================
#                   START BOT
# ============================================================


async def main() -> None:
    log_info("Starting Telegram bot...")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    asyncio.create_task(poller(bot))

    log_info("Bot is running. Waiting for events...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
