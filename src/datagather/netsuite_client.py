import requests
from requests_oauthlib import OAuth1

from .config import load_env, require_env

def run_suiteql_paged(query: str, limit: int = 1000, verbose: bool = True) -> list[dict]:
    load_env()

    account_id = require_env("NS_ACCOUNT_ID")
    base_url = require_env("NS_REST_BASE_URL").rstrip("/")

    consumer_key = require_env("NS_CONSUMER_KEY")
    consumer_secret = require_env("NS_CONSUMER_SECRET")
    token_id = require_env("NS_TOKEN_ID")
    token_secret = require_env("NS_TOKEN_SECRET")

    auth = OAuth1(
        client_key=consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=token_id,
        resource_owner_secret=token_secret,
        realm=account_id,
        signature_method="HMAC-SHA256",
    )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Prefer": "transient",  # you confirmed you need this :contentReference[oaicite:4]{index=4}
    }

    all_rows: list[dict] = []
    offset = 0

    while True:
        url = f"{base_url}/services/rest/query/v1/suiteql?limit={limit}&offset={offset}"
        resp = requests.post(url, json={"q": query}, headers=headers, auth=auth, timeout=30)

        if resp.status_code != 200:
            raise RuntimeError(f"SuiteQL failed (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        rows = data.get("items", [])
        all_rows.extend(rows)

        if verbose:
            print(f"Pulled {len(rows)} rows at offset {offset} (total so far: {len(all_rows)})")

        if not data.get("hasMore"):
            break

        offset += limit

    return all_rows
