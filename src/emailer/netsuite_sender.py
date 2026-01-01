import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def send_email_netsuite(
    *,
    to: str,
    subject: str,
    body: str,
    author: int | None = None,
    dry_run: bool | None = None,
    log_path: str = "logs/sent_email.jsonl",
    timeout_sec: int = 30,
) -> dict[str, Any]:
    """
    Sends an email via a NetSuite RESTlet.

    Requires .env:
      NS_ACCOUNT_ID
      NS_CONSUMER_KEY
      NS_CONSUMER_SECRET
      NS_TOKEN_ID
      NS_TOKEN_SECRET
      NS_RESTLET_URL

    Optional .env:
      DRY_RUN=true|false
    """
    load_dotenv()

    account_id = _require_env("NS_ACCOUNT_ID")
    restlet_url = _require_env("NS_RESTLET_URL")

    consumer_key = _require_env("NS_CONSUMER_KEY")
    consumer_secret = _require_env("NS_CONSUMER_SECRET")
    token_id = _require_env("NS_TOKEN_ID")
    token_secret = _require_env("NS_TOKEN_SECRET")

    if dry_run is None:
        dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    auth = OAuth1(
        client_key=consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=token_id,
        resource_owner_secret=token_secret,
        realm=account_id,
        signature_method="HMAC-SHA256",
    )

    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    payload: dict[str, Any] = {"to": to, "subject": subject, "body": body}
    if author is not None:
        payload["author"] = author

    # If dry run, don't send—just log what would have happened
    if dry_run:
        result = {"ok": True, "dry_run": True, "http": None, "response": None}
        _log_send_attempt(log_path=log_path, payload=payload, result=result)
        return result

    resp = requests.post(
        restlet_url, headers=headers, auth=auth, json=payload, timeout=timeout_sec
    )

    # Try to parse JSON response safely
    try:
        response_data = resp.json()
    except Exception:
        response_data = {"raw_text": resp.text}

    result = {
        "ok": resp.status_code == 200 and bool(response_data.get("ok", False)),
        "dry_run": False,
        "http": resp.status_code,
        "response": response_data,
    }

    _log_send_attempt(log_path=log_path, payload=payload, result=result)

    if not result["ok"]:
        raise RuntimeError(f"NetSuite send failed (HTTP {resp.status_code}): {resp.text}")

    return result


def _log_send_attempt(*, log_path: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
    Path(os.path.dirname(log_path) or ".").mkdir(exist_ok=True)

    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "to": payload.get("to"),
        "subject": payload.get("subject"),
        "dry_run": result.get("dry_run"),
        "http": result.get("http"),
        "ok": result.get("ok"),
        "response": result.get("response"),
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
