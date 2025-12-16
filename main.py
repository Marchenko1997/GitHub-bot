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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  
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
    if not commits:
        return f"📌 Новый push в <b>{repo}</b> ({branch})"
    lines = []
    for c in commits:
        msg = (c.get("message") or "")[:80]   
        url = c.get("url", "")
        lines.append(f"• <code>{msg}</code>\n  🔗 <a href=\"{url}\">commit</a>")

    return f"📌 <b>Push в {repo}</b> ({branch})\n" + "\n".join(lines)


def format_pr(payload: Dict[str, Any]) -> Optional[str]:
 
    action = payload.get("action")

    pr = payload.get("pull_request") or {}
    repo = payload.get("repository", {}).get("full_name", "unknown")

    title = (pr.get("title") or "")[:100]
    number = pr.get("number")
    url = pr.get("html_url", "")


    if action == "opened":
        prefix = "📝 Открыт PR"
    elif action == "closed" and pr.get("merged"):
        prefix = "✅ Смёржен PR"
    elif action == "closed":
        prefix = "🛑 Закрыт PR"
    else:
     
        return None

    return (
        f"{prefix} #{number} в <code>{repo}</code>\n"
        f"{title}\n"
        f'🔗 <a href="{url}">Открыть PR</a>'
    )

def format_new_repo_from_webhook(payload: Dict[str, Any]) -> str:
    repo = payload.get("repository") or {}
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

def verify_signature(body: bytes, signature_header: str) -> None:
    try:
        algo, sig_hex = signature_header.split("=", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad signature header format")

    if algo != "sha256":
        raise HTTPException(status_code=400, detail="Unsupported signature algorithm")

    mac = hmac.new(GITHUB_WEBHOOK_SECRET, msg = body, digestmod=hashlib.sha256)
    expected = mac.hexdigest()

    if not hmac.compare_digest(expected, sig_hex):

        raise HTTPException(status_code=401, detail="Invalid signature")


@app.post("/github-webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),  
    x_hub_signature_256: str = Header(..., alias="X-Hub-Signature-256"), 
):

    body = await request.body()

    verify_signature(body, x_hub_signature_256)

    payload = json.loads(body.decode("utf-8"))
    log_info(f"Webhook event: {x_github_event}")

    text: Optional[str] = None

    if x_github_event == "push":
        text = format_push(payload)

    elif x_github_event == "pull_request":
        text = format_pr(payload)
        if text is None:
            log_info(f"Ignore PR action: {payload.get('action')}")
            return {"status": "ignored"}

    elif x_github_event == "repository":

        action = payload.get("action")
        if action != "created":
            log_info(f"Ignore repository action: {action}")
            return {"status": "ignored"}
        text = format_new_repo_from_webhook(payload)

    else:

        log_info(f"Ignore event: {x_github_event}")
        return {"status": "ignored"}

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        log_info("✅ Telegram message sent")
    except Exception as e:
        log_error(f"Telegram send error: {e}")
        raise HTTPException(status_code=500, detail="Telegram send failed")

    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "ok", "message": "GitHub → Telegram webhook bot"}


@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    log_info("Starting FastAPI GitHub webhook server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,  
    )
