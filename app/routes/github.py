from fastapi import APIRouter, Request, Header
from ..verify import verify_signature
from ..logger import log_info
from ..bot import bot
from ..config import TELEGRAM_CHAT_ID

from ..formatters.push import format_push
from ..formatters.pull_request import format_pr
from ..formatters.repository import format_repository
import json


router = APIRouter()


@router.post("/github-webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(..., alias="X-Hub-Signature-256"),
):

    body = await request.body()
    verify_signature(body, x_hub_signature_256)

    payload = json.loads(body)
    log_info(f"Webhook event: {x_github_event}")

    text = None

    if x_github_event == "push":
        text = format_push(payload)

    elif x_github_event == "pull_request":
        text = format_pr(payload)

    elif x_github_event == "repository":
        if payload.get("action") == "created":
            text = format_repository(payload)

    if not text:
        return {"status": "ignored"}

    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="HTML")

    return {"status": "ok"}
