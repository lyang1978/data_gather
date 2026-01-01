import json
import os
from datetime import date
from typing import Any

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def stamp_last_inq_sent_date_netsuite(
    *,
    po_ids: list[str] | list[int],
    sent_date: str | None = None,  # YYYY-MM-DD
    timeout_sec: int = 30,
) -> dict[str, Any]:
    """
    Calls NetSuite RESTlet to update custbody_last_inq_sent_date_ on Purchase Orders.

    Requires .env:
      NS_ACCOUNT_ID
      NS_CONSUMER_KEY
      NS_CONSUMER_SECRET
      NS_TOKEN_ID
      NS_TOKEN_SECRET
      NS_STAMP_RESTLET_URL
    """
    load_dotenv()

    account_id = _require_env("NS_ACCOUNT_ID")
    restlet_url = _require_env("NS_STAMP_RESTLET_URL")

    consumer_key = _require_env("NS_CONSUMER_KEY")
    consumer_secret = _require_env("NS_CONSUMER_SECRET")
    token_id = _require_env("NS_TOKEN_ID")
    token_secret = _require_env("NS_TOKEN_SECRET")

    auth = OAuth1(
        client_key=consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=token_id,
        resource_owner_secret=token_secret,
        realm=account_id,
        signature_method="HMAC-SHA256",
    )

    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    if sent_date is None:
        sent_date = date.today().isoformat()

    payload = {"po_ids": po_ids, "sent_date": sent_date}

    resp = requests.post(restlet_url, headers=headers, auth=auth, json=payload, timeout=timeout_sec)

    try:
        data = resp.json()
    except Exception:
        data = {"raw_text": resp.text}

    if resp.status_code != 200:
        raise RuntimeError(f"Stamp RESTlet failed (HTTP {resp.status_code}): {resp.text}")

    return data
