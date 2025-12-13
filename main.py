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

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
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
        return {"last_event_id": None, "repos": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        log_warn("State file corrupted — resetting.")
        return {"last_event_id": None, "repos": []}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
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
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise RuntimeError(f"GitHub events API error: {resp.status}")
        return await resp.json()


async def fetch_user_repos(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?per_page=100"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}",
        "User-Agent": "gh-telegram-notify-bot",
    }
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise RuntimeError(f"GitHub repos API error: {resp.status}")
        return await resp.json()


# ============================================================
#                  EVENT FILTERS
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
#                  FORMATTERS
# ============================================================


def format_push(event: Dict[str, Any]) -> str:
    repo = (event.get("repo") or {}).get("name", "unknown")
    commits = (event.get("payload") or {}).get("commits", [])
    if not commits:
        return f"📌 Новый push в <b>{repo}</b>"
    commit_msgs = "\n".join(f"- {c['message']}" for c in commits)
    return f"📌 Новый push в <b>{repo}</b>:\n{commit_msgs}"


def format_repo_created(event: Dict[str, Any]) -> str:
    repo = (event.get("repo") or {}).get("name")
    return f"🆕 Создан репозиторий: <b>{repo}</b>"


def format_merged(event: Dict[str, Any]) -> str:
    pr = (event.get("payload") or {}).get("pull_request") or {}
    repo = pr.get("base", {}).get("repo", {}).get("full_name", "unknown")
    title = pr.get("title", "")
    number = pr.get("number", "")
    url = pr.get("html_url", "")
    return f"✅ Merge PR #{number} в <b>{repo}</b>\n📝 {title}\n🔗 {url}"


def format_new_repo(repo: Dict[str, Any]) -> str:
    return (
        f"🆕 <b>Новый репозиторий</b>\n"
        f"📦 {repo.get('name')}\n"
        f"🗂 Язык: {repo.get('language')}\n"
        f"🔒 Приватность: {'private' if repo.get('private') else 'public'}"
    )


# ============================================================
#                MESSAGE BUILDER
# ============================================================


def build_messages(event: Dict[str, Any]) -> Optional[str]:
    if is_push_event(event):
        return format_push(event)
    if is_merge_event(event):
        return format_merged(event)
    if is_new_repo_event(event):
        return format_repo_created(event)
    return None


# ============================================================
#           FULL CHECK: EVENTS + NEW REPOSITORIES
# ============================================================


async def notify_new_events(bot: Bot) -> None:
    log_info("Checking GitHub...")

    state = load_state()
    last_event_id = state.get("last_event_id")

    async with aiohttp.ClientSession() as session:
        events = await fetch_github_events(session)
        repos = await fetch_user_repos(session)

    # --- Check new repos -------------------------------------
    repo_names = {r["name"] for r in repos}
    old_repos = set(state.get("repos", []))
    new_repos = repo_names - old_repos

    if new_repos:
        for repo in repos:
            if repo["name"] in new_repos:
                await bot.send_message(
                    chat_id=int(TELEGRAM_CHAT_ID),
                    text=format_new_repo(repo),
                    parse_mode="HTML",
                )
        state["repos"] = list(repo_names)
        save_state(state)
        log_info(f"New repositories detected: {new_repos}")

    # --- Check events -----------------------------------------
    new_events: List[Dict[str, Any]] = []
    for e in events:
        if last_event_id and e["id"] == last_event_id:
            break
        new_events.append(e)

    if not new_events:
        log_info("No new events.")
    else:
        new_events.reverse()
        for e in new_events:
            msg = build_messages(e)
            if msg:
                await bot.send_message(
                    chat_id=int(TELEGRAM_CHAT_ID),
                    text=msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
        state["last_event_id"] = events[0]["id"]
        save_state(state)


# ============================================================
#                     POLLER
# ============================================================


async def poller(bot: Bot) -> None:
    log_info("Initializing poller...")

    state = load_state()

    if not state.get("repos"):
        async with aiohttp.ClientSession() as session:
            repos = await fetch_user_repos(session)
        state["repos"] = [r["name"] for r in repos]
        save_state(state)
        log_info("Initial repo list saved.")

    if not state.get("last_event_id"):
        async with aiohttp.ClientSession() as session:
            events = await fetch_github_events(session)
        if events:
            state["last_event_id"] = events[0]["id"]
            save_state(state)
            log_info("Initial last_event_id saved.")

    while True:
        try:
            await notify_new_events(bot)
        except Exception as e:
            log_error(str(e))
        await asyncio.sleep(POLL_INTERVAL)


# ============================================================
#                    START BOT
# ============================================================


async def main() -> None:
    log_info("Starting bot...")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    log_info("Bot is running...")


    async with bot:
        await asyncio.gather(dp.start_polling(bot), poller(bot))


if __name__ == "__main__":
    asyncio.run(main())
