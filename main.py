import asyncio
import json
import os
from typing import Any, Dict, List, Optional
import aiohttp
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# ЛОГГЕР
# ============================================================
def log_info(message: str) -> None:
    print(f"\033[92m[INFO]\033[0m {message}")


def log_warn(message: str) -> None:
    print(f"\033[93m[WARN]\033[0m {message}")


def log_error(message: str) -> None:
    print(f"\033[91m[ERROR]\033[0m {message}")


# ============================================================
# .ENV
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
STATE_FILE = os.getenv("STATE_FILE", "state.json")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GITHUB_TOKEN, GITHUB_USERNAME]):
    raise RuntimeError("Missing required env variables in .env")

log_info(f"Config loaded: user={GITHUB_USERNAME}")


# ============================================================
# STATE
# ============================================================
def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        log_info("No state file found, starting fresh")
        return {"last_event_id": None, "repos": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_warn(f"State file corrupted ({e}) — resetting.")
        return {"last_event_id": None, "repos": []}


def save_state(state: Dict[str, Any]) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_error(f"Failed to save state: {e}")


# ============================================================
# GITHUB API
# ============================================================
async def fetch_github_events(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/events?per_page=30"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}",
        "User-Agent": "gh-telegram-notify-bot",
    }
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            text = await resp.text()
            log_error(f"GitHub events API error {resp.status}: {text[:200]}")
            raise RuntimeError(f"GitHub events API error: {resp.status}")
        return await resp.json()


async def fetch_user_repos(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?per_page=100&sort=updated"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}",
        "User-Agent": "gh-telegram-notify-bot",
    }
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            text = await resp.text()
            log_error(f"GitHub repos API error {resp.status}: {text[:200]}")
            raise RuntimeError(f"GitHub repos API error: {resp.status}")
        return await resp.json()


# ============================================================
# EVENT FILTERS
# ============================================================
def is_push_event(event: Dict[str, Any]) -> bool:
    return event.get("type") == "PushEvent"


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
    return bool((payload.get("pull_request") or {}).get("merged"))


# ============================================================
# FORMATTERS
# ============================================================
def format_push(event: Dict[str, Any]) -> str:
    repo = (event.get("repo") or {}).get("name", "unknown")
    commits = (event.get("payload") or {}).get("commits", [])
    if not commits:
        return f"📌 Новый push в <b>{repo}</b>"
    commit_msgs = "\n".join(
        f"• {c['message'][:50]}{'...' if len(c['message']) > 50 else ''}"
        for c in commits[:3]
    )
    return f"📌 <b>Push в {repo}</b>\n<code>{commit_msgs}</code>"


def format_repo_created(event: Dict[str, Any]) -> str:
    repo = (event.get("repo") or {}).get("name", "unknown")
    return f"🆕 <b>Создан репозиторий: {repo}</b>"


def format_merged(event: Dict[str, Any]) -> str:
    pr = (event.get("payload") or {}).get("pull_request") or {}
    repo = pr.get("base", {}).get("repo", {}).get("full_name", "unknown")
    title = pr.get("title", "")[:100]
    number = pr.get("number", 0)
    url = pr.get("html_url", "")
    return f"✅ <b>Merged PR #{number}</b> в <code>{repo}</code>\n📝 {title}\n🔗 <a href='{url}'>Открыть PR</a>"


def format_new_repo(repo: Dict[str, Any]) -> str:
    name = repo.get("name", "unknown")
    lang = repo.get("language", "не указан")
    private = "private" if repo.get("private") else "public"
    url = repo.get("html_url", "")
    return (
        f"🆕 <b>Новый репозиторий: {name}</b>\n"
        f"🗂 Язык: <code>{lang}</code>\n"
        f"🔒 {private.title()}\n"
        f"🔗 <a href='{url}'>Открыть репозиторий</a>"
    )


# ============================================================
# MESSAGE BUILDER
# ============================================================
def build_message(event: Dict[str, Any]) -> Optional[str]:
    if is_push_event(event):
        return format_push(event)
    if is_merge_event(event):
        return format_merged(event)
    if is_new_repo_event(event):
        return format_repo_created(event)
    return None


# ============================================================
# MAIN LOGIC
# ============================================================
async def check_and_notify(bot: Bot, state: Dict[str, Any]) -> bool:
    """Возвращает True если были уведомления"""
    notified = False

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10)
    ) as session:
        events = await fetch_github_events(session)
        repos = await fetch_user_repos(session)

    log_info(f"Found {len(repos)} repos, {len(events)} events")

    # 1. Новые репозитории
    repo_names = {r["name"] for r in repos}
    old_repos = set(state.get("repos", []))
    new_repos = repo_names - old_repos

    if new_repos:
        log_info(f"🆕 New repos: {new_repos}")
        for repo in repos:
            if repo["name"] in new_repos:
                await bot.send_message(
                    chat_id=int(TELEGRAM_CHAT_ID),
                    text=format_new_repo(repo),
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )
                notified = True
        state["repos"] = list(repo_names)

    # 2. Новые события
    last_event_id = state.get("last_event_id")
    new_events = []

    for event in events:
        if last_event_id and event["id"] == last_event_id:
            break
        new_events.append(event)

    if new_events:
        log_info(f"📢 New events: {len(new_events)}")
        new_events.reverse()  # Новые сверху
        for event in new_events:
            msg = build_message(event)
            if msg:
                await bot.send_message(
                    chat_id=int(TELEGRAM_CHAT_ID),
                    text=msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                notified = True

        state["last_event_id"] = events[0]["id"]

    if notified:
        save_state(state)
        log_info("✅ Notifications sent")
    else:
        log_info("ℹ️ No new activity")

    return notified


# ============================================================
# POLLER
# ============================================================
async def poller(bot: Bot) -> None:
    log_info("🚀 Starting GitHub poller...")

    # Инициализация состояния
    state = load_state()

    if not state.get("repos"):
        log_info("📂 Initializing repos...")
        async with aiohttp.ClientSession() as session:
            repos = await fetch_user_repos(session)
            state["repos"] = [r["name"] for r in repos]
            save_state(state)
        log_info(f"✅ Saved {len(state['repos'])} repos")

    if not state.get("last_event_id"):
        log_info("📊 Initializing events...")
        async with aiohttp.ClientSession() as session:
            events = await fetch_github_events(session)
            if events:
                state["last_event_id"] = events[0]["id"]
                save_state(state)
                log_info("✅ Events initialized")

    cycle = 0
    while True:
        cycle += 1
        try:
            log_info(f"🔄 Cycle #{cycle} ({asyncio.get_event_loop().time():.0f})")
            await check_and_notify(bot, state)
        except Exception as e:
            log_error(f"❌ Check failed: {e}")
            import traceback

            log_error(traceback.format_exc())

        await asyncio.sleep(POLL_INTERVAL)


# ============================================================
# MAIN
# ============================================================
async def main() -> None:
    log_info("🤖 Starting GitHub → Telegram bot...")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Тестовое сообщение
    try:
        await bot.send_message(
            chat_id=int(TELEGRAM_CHAT_ID),
            text="🚀 <b>GitHub Notify Bot started!</b>\nПроверки каждые "
            + f"{POLL_INTERVAL}с на push/merge/новые репозитории.",
            parse_mode="HTML",
        )
        log_info("✅ Test message sent")
    except Exception as e:
        log_error(f"❌ Test message failed: {e}")

    # Запуск
    async with bot:
        await asyncio.gather(poller(bot), dp.start_polling(bot))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_info("👋 Bot stopped by user")
    except Exception as e:
        log_error(f"💥 Fatal error: {e}")
