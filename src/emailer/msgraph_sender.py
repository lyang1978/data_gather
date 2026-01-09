"""
Microsoft Graph Email Sender

Sends/drafts emails via Microsoft Graph API using OAuth2 client credentials flow.

Functions:
    - create_draft_msgraph: Create email draft in Drafts folder (for manual review)
    - send_email_msgraph: Send email directly
    - send_email_with_attachment: Send email with HTML attachment (for reports)

Environment variables:
    MICROSOFT_CLIENT_ID     - Azure AD App client ID
    MICROSOFT_CLIENT_SECRET - Azure AD App client secret
    MICROSOFT_TENANT_ID     - Azure AD tenant ID
    MICROSOFT_USER_EMAIL    - Email address to send from (must have permissions)
    DRY_RUN                 - If "true", log but don't actually create draft/send
    CARBON_COPY             - Optional CC recipients (semicolon-separated for multiple)
"""

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


def _log_email(log_record: dict[str, Any]) -> None:
    """Append email record to JSONL log."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "email_log.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_record) + "\n")


def get_access_token() -> str:
    """
    Get OAuth2 access token using client credentials flow.

    Returns:
        Access token string

    Raises:
        Exception if token request fails
    """
    tenant_id = os.getenv("MICROSOFT_TENANT_ID")
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

    if not all([tenant_id, client_id, client_secret]):
        raise ValueError("Missing Microsoft credentials in environment variables")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }

    response = requests.post(token_url, data=data)

    if response.status_code != 200:
        raise Exception(f"Failed to get access token: {response.status_code} - {response.text}")

    return response.json()["access_token"]


def create_draft_msgraph(
    *,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
) -> dict[str, Any]:
    """
    Create an email draft in the user's Drafts folder (for manual review before sending).

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        cc: Optional CC recipients, semicolon-separated (defaults to CARBON_COPY env var)

    Returns:
        Dict with ok, draft_id, web_link, etc.
    """
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    from_email = os.getenv("MICROSOFT_USER_EMAIL")
    cc = cc or os.getenv("CARBON_COPY")

    if not from_email:
        raise ValueError("MICROSOFT_USER_EMAIL not set in environment")

    # Build draft message payload (HTML format for proper table rendering)
    draft_payload = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body,
        },
        "toRecipients": [
            {"emailAddress": {"address": to}}
        ],
    }

    if cc:
        # Support multiple CC recipients separated by semicolon
        cc_addresses = [addr.strip() for addr in cc.split(";") if addr.strip()]
        if cc_addresses:
            draft_payload["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_addresses
            ]

    log_record = {
        "timestamp": datetime.now().isoformat(),
        "action": "create_draft",
        "to": to,
        "cc": cc,
        "subject": subject,
        "body": body,
        "dry_run": dry_run,
        "from": from_email,
    }

    if dry_run:
        log_record["status"] = "dry_run"
        _log_email(log_record)
        return {
            "ok": True,
            "dry_run": True,
            "message": "Draft logged (dry-run mode)",
            "to": to,
            "subject": subject,
        }

    try:
        access_token = get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Create draft in Drafts folder
        drafts_url = f"https://graph.microsoft.com/v1.0/users/{from_email}/messages"
        response = requests.post(drafts_url, headers=headers, json=draft_payload)

        if response.status_code == 201:
            resp_data = response.json()
            draft_id = resp_data.get("id")
            web_link = resp_data.get("webLink")

            log_record["status"] = "drafted"
            log_record["draft_id"] = draft_id
            log_record["web_link"] = web_link
            _log_email(log_record)

            return {
                "ok": True,
                "dry_run": False,
                "message": "Draft created in Drafts folder",
                "draft_id": draft_id,
                "web_link": web_link,
                "to": to,
                "subject": subject,
            }
        else:
            error_msg = response.text
            log_record["status"] = "failed"
            log_record["error"] = error_msg
            log_record["response_code"] = response.status_code
            _log_email(log_record)

            return {
                "ok": False,
                "dry_run": False,
                "error": f"Graph API error: {response.status_code} - {error_msg}",
                "to": to,
                "subject": subject,
            }

    except Exception as e:
        log_record["status"] = "failed"
        log_record["error"] = str(e)
        _log_email(log_record)
        return {
            "ok": False,
            "dry_run": False,
            "error": str(e),
            "to": to,
            "subject": subject,
        }


def send_email_msgraph(
    *,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
) -> dict[str, Any]:
    """
    Send email via Microsoft Graph API.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        cc: Optional CC recipients, semicolon-separated (defaults to CARBON_COPY env var)

    Returns:
        Dict with ok, dry_run, message_id, etc.
    """
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    from_email = os.getenv("MICROSOFT_USER_EMAIL")
    cc = cc or os.getenv("CARBON_COPY")

    if not from_email:
        raise ValueError("MICROSOFT_USER_EMAIL not set in environment")

    # Build email payload
    email_payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body,
            },
            "toRecipients": [
                {"emailAddress": {"address": to}}
            ],
        },
        "saveToSentItems": "true",
    }

    # Add CC if provided (supports semicolon-separated list)
    if cc:
        cc_addresses = [addr.strip() for addr in cc.split(";") if addr.strip()]
        if cc_addresses:
            email_payload["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_addresses
            ]

    # Log to JSONL regardless of dry_run
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "sent_email.jsonl"

    log_record = {
        "timestamp": datetime.now().isoformat(),
        "to": to,
        "cc": cc,
        "subject": subject,
        "body": body,
        "dry_run": dry_run,
        "from": from_email,
    }

    if dry_run:
        log_record["status"] = "dry_run"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_record) + "\n")

        return {
            "ok": True,
            "dry_run": True,
            "message": "Email logged (dry-run mode)",
            "to": to,
            "subject": subject,
        }

    # Get access token and send
    try:
        access_token = get_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Send email endpoint
        send_url = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"

        response = requests.post(send_url, headers=headers, json=email_payload)

        if response.status_code == 202:
            # Success - 202 Accepted is the expected response for sendMail
            log_record["status"] = "sent"
            log_record["response_code"] = 202
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_record) + "\n")

            return {
                "ok": True,
                "dry_run": False,
                "message": "Email sent successfully",
                "to": to,
                "subject": subject,
            }
        else:
            # Error
            error_msg = response.text
            log_record["status"] = "failed"
            log_record["error"] = error_msg
            log_record["response_code"] = response.status_code
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_record) + "\n")

            return {
                "ok": False,
                "dry_run": False,
                "error": f"Graph API error: {response.status_code} - {error_msg}",
                "to": to,
                "subject": subject,
            }

    except Exception as e:
        log_record["status"] = "failed"
        log_record["error"] = str(e)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_record) + "\n")

        return {
            "ok": False,
            "dry_run": False,
            "error": str(e),
            "to": to,
            "subject": subject,
        }


def send_report_email(
    *,
    to: str,
    subject: str,
    body: str,
    attachment_path: str | Path,
    attachment_name: str | None = None,
) -> dict[str, Any]:
    """
    Send an email with an HTML file attachment (for inquiry reports).

    This function ignores DRY_RUN - reports are always sent.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        attachment_path: Path to the HTML file to attach
        attachment_name: Optional filename for attachment (defaults to original filename)

    Returns:
        Dict with ok, message, etc.
    """
    from_email = os.getenv("MICROSOFT_USER_EMAIL")

    if not from_email:
        raise ValueError("MICROSOFT_USER_EMAIL not set in environment")

    attachment_path = Path(attachment_path)
    if not attachment_path.exists():
        return {
            "ok": False,
            "error": f"Attachment not found: {attachment_path}",
        }

    attachment_name = attachment_name or attachment_path.name

    # Read and base64 encode the attachment
    with open(attachment_path, "rb") as f:
        attachment_content = base64.b64encode(f.read()).decode("utf-8")

    # Build email payload with attachment
    email_payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body,
            },
            "toRecipients": [
                {"emailAddress": {"address": to}}
            ],
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": attachment_name,
                    "contentType": "text/html",
                    "contentBytes": attachment_content,
                }
            ],
        },
        "saveToSentItems": "true",
    }

    log_record = {
        "timestamp": datetime.now().isoformat(),
        "action": "send_report",
        "to": to,
        "subject": subject,
        "attachment": attachment_name,
        "from": from_email,
    }

    try:
        access_token = get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        send_url = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"
        response = requests.post(send_url, headers=headers, json=email_payload)

        if response.status_code == 202:
            log_record["status"] = "sent"
            _log_email(log_record)
            return {
                "ok": True,
                "message": f"Report sent to {to}",
                "to": to,
                "attachment": attachment_name,
            }
        else:
            error_msg = response.text
            log_record["status"] = "failed"
            log_record["error"] = error_msg
            log_record["response_code"] = response.status_code
            _log_email(log_record)
            return {
                "ok": False,
                "error": f"Graph API error: {response.status_code} - {error_msg}",
            }

    except Exception as e:
        log_record["status"] = "failed"
        log_record["error"] = str(e)
        _log_email(log_record)
        return {
            "ok": False,
            "error": str(e),
        }


def test_auth() -> dict[str, Any]:
    """
    Test Microsoft Graph authentication by getting an access token.

    Returns:
        Dict with ok, message, and token_preview
    """
    try:
        token = get_access_token()
        return {
            "ok": True,
            "message": "Authentication successful",
            "token_preview": f"{token[:20]}...{token[-10:]}",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }


if __name__ == "__main__":
    # Quick test
    print("Testing Microsoft Graph authentication...")
    result = test_auth()
    print(json.dumps(result, indent=2))
