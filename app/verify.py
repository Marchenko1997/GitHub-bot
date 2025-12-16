import hmac
import hashlib
from fastapi import HTTPException
from .config import GITHUB_WEBHOOK_SECRET


def verify_signature(body: bytes, signature_header: str):
    try:
        algo, sig_hex = signature_header.split("=", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad signature header format")

    if algo != "sha256":
        raise HTTPException(status_code=400, detail="Unsupported signature algorithm")

    mac = hmac.new(GITHUB_WEBHOOK_SECRET, msg=body, digestmod=hashlib.sha256)
    expected = mac.hexdigest()

    if not hmac.compare_digest(expected, sig_hex):
        raise HTTPException(status_code=401, detail="Invalid signature")
