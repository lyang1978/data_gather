#!/usr/bin/env python3
"""
PO Vendor Inquiry CLI

Standalone CLI entrypoint for running vendor PO status inquiry emails.
Supports both deterministic (no-LLM) and agent-based (LLM) modes.

Usage:
    python cli.py --help
    python cli.py --dry-run                    # Safe test run, no emails sent
    python cli.py --live --max-emails 5        # Send up to 5 vendor emails
    python cli.py --test-vendor someone@co.com # Filter to single vendor for testing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# -----------------------------------------------------------------------------
# HTML EXPORT
# -----------------------------------------------------------------------------

def generate_html_report(
    *,
    run_info: dict[str, Any],
    briefs: list[dict[str, Any]],
    emails: list[dict[str, Any]],
    analysis_stats: dict[str, Any],
    dg_stats: dict[str, Any],
) -> str:
    """Generate an HTML report of all emails sent/drafted."""

    mode = run_info.get("mode", "unknown")
    dry_run = run_info.get("dry_run", True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PO Vendor Inquiry Report - {timestamp}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{ color: #333; border-bottom: 3px solid #2196F3; padding-bottom: 10px; }}
        h2 {{ color: #1976D2; margin-top: 30px; }}
        h3 {{ color: #444; margin-top: 20px; }}
        .header {{
            background: linear-gradient(135deg, #1976D2, #2196F3);
            color: white;
            padding: 20px 30px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .header h1 {{ color: white; border: none; margin: 0; }}
        .header p {{ margin: 5px 0 0 0; opacity: 0.9; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #1976D2;
        }}
        .stat-card .label {{
            color: #666;
            font-size: 0.9em;
        }}
        .email-card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin: 20px 0;
            overflow: hidden;
        }}
        .email-header {{
            background: #f8f9fa;
            padding: 15px 20px;
            border-bottom: 1px solid #e0e0e0;
        }}
        .email-header .vendor {{
            font-size: 1.2em;
            font-weight: bold;
            color: #333;
        }}
        .email-header .meta {{
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        .email-subject {{
            background: #e3f2fd;
            padding: 10px 20px;
            font-weight: bold;
            color: #1565C0;
        }}
        .email-body {{
            padding: 20px;
            white-space: pre-wrap;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            background: #fafafa;
            border-top: 1px solid #e0e0e0;
        }}
        .status-badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .status-dry-run {{ background: #fff3e0; color: #e65100; }}
        .status-sent {{ background: #e8f5e9; color: #2e7d32; }}
        .status-failed {{ background: #ffebee; color: #c62828; }}
        .status-skipped {{ background: #f5f5f5; color: #616161; }}
        .po-list {{
            margin: 10px 0;
            padding: 10px 15px;
            background: #f5f5f5;
            border-radius: 4px;
        }}
        .po-item {{
            display: inline-block;
            background: white;
            padding: 2px 8px;
            margin: 2px;
            border-radius: 4px;
            font-size: 0.85em;
            border: 1px solid #ddd;
        }}
        .po-item.past-due {{ border-color: #f44336; color: #c62828; }}
        .po-item.due {{ border-color: #ff9800; color: #e65100; }}
        .summary-section {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin: 20px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{ background: #f5f5f5; font-weight: 600; }}
        .toc {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin: 20px 0;
        }}
        .toc ul {{ margin: 10px 0; padding-left: 20px; }}
        .toc a {{ color: #1976D2; text-decoration: none; }}
        .toc a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>PO Vendor Inquiry Report</h1>
        <p>Generated: {timestamp} | Mode: {"DRY-RUN" if dry_run else "LIVE"} | Engine: {mode}</p>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="value">{dg_stats.get('po_count', 0)}</div>
            <div class="label">Total POs</div>
        </div>
        <div class="stat-card">
            <div class="value">{dg_stats.get('line_count', 0)}</div>
            <div class="label">Total Lines</div>
        </div>
        <div class="stat-card">
            <div class="value">{analysis_stats.get('eligible_for_inquiry_count', 0)}</div>
            <div class="label">Eligible for Inquiry</div>
        </div>
        <div class="stat-card">
            <div class="value">{len(emails)}</div>
            <div class="label">Emails Generated</div>
        </div>
    </div>

    <div class="summary-section">
        <h2>Analysis Summary</h2>
        <table>
            <tr><th>Metric</th><th>Count</th></tr>
            <tr><td>Normal (not yet due)</td><td>{analysis_stats.get('normal_count', 0)}</td></tr>
            <tr><td>Due (within 14 days)</td><td>{analysis_stats.get('due_count', 0)}</td></tr>
            <tr><td>Past Due</td><td>{analysis_stats.get('past_due_count', 0)}</td></tr>
            <tr><td>Missing Due Dates</td><td>{analysis_stats.get('needs_buyer_data_count', 0)}</td></tr>
        </table>
    </div>

    <div class="toc">
        <h2>Table of Contents</h2>
        <ul>
"""

    for i, email in enumerate(emails, start=1):
        vendor_email = email.get("to", "unknown")
        html += f'            <li><a href="#email-{i}">{i}. {vendor_email}</a></li>\n'

    html += """        </ul>
    </div>

    <h2>Email Details</h2>
"""

    for i, email in enumerate(emails, start=1):
        vendor_email = email.get("to", "unknown")
        vendor_name = email.get("vendor", "")
        subject = email.get("subject", "(no subject)")
        body = email.get("body", "(no body)")
        status = email.get("status", "unknown")
        po_count = email.get("po_count", 0)
        pos = email.get("pos", [])

        # Determine status badge class
        if status == "dry_run":
            badge_class = "status-dry-run"
            badge_text = "Dry Run"
        elif status == "sent":
            badge_class = "status-sent"
            badge_text = "Sent"
        elif status == "failed":
            badge_class = "status-failed"
            badge_text = "Failed"
        else:
            badge_class = "status-skipped"
            badge_text = status.title()

        # Build PO list with state coloring
        po_items = ""
        for po in pos:
            state = po.get("state", "")
            state_class = "past-due" if state == "Past Due" else ("due" if state == "Due" else "")
            po_items += f'<span class="po-item {state_class}">{po.get("po_number", "?")} ({state})</span>'

        # Escape HTML in body
        body_escaped = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        html += f"""
    <div class="email-card" id="email-{i}">
        <div class="email-header">
            <div class="vendor">{i}. {vendor_name} &lt;{vendor_email}&gt;</div>
            <div class="meta">
                <span class="status-badge {badge_class}">{badge_text}</span>
                &nbsp;|&nbsp; {po_count} PO(s)
            </div>
            <div class="po-list">{po_items if po_items else "No POs"}</div>
        </div>
        <div class="email-subject">Subject: {subject}</div>
        <div class="email-body">{body_escaped}</div>
    </div>
"""

    html += """
    <div class="summary-section">
        <h2>Run Configuration</h2>
        <table>
            <tr><th>Setting</th><th>Value</th></tr>
"""

    for key, value in run_info.items():
        html += f"            <tr><td>{key}</td><td>{value}</td></tr>\n"

    html += """        </table>
    </div>

</body>
</html>
"""

    return html


def save_html_report(html: str, output_path: str | None = None) -> str:
    """Save HTML report to file. Returns the path used."""
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"logs/inquiry_report_{timestamp}.html"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def _setup_path() -> None:
    """Ensure src directory is in Python path for imports."""
    src_dir = os.path.dirname(os.path.abspath(__file__))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)


_setup_path()

from datagather.datagather import datagather
from analyzer.analyzer import analyze
from emailer.netsuite_sender import send_email_netsuite
from emailer.netsuite_stamper import stamp_last_inq_sent_date_netsuite


# -----------------------------------------------------------------------------
# BRIEF BUILDING (deterministic, no LLM)
# -----------------------------------------------------------------------------

def build_vendor_briefs(
    analysis_obj: dict[str, Any],
    *,
    max_vendors: int = 50,
    max_pos_per_vendor: int = 20,
    max_lines_per_po: int = 50,
) -> dict[str, Any]:
    """
    Build vendor briefs from analyzer output.

    Only includes POs where recommended_action == 'inquire_vendor'.
    Caps briefs to avoid excessive context in LLM calls.

    Returns: {"briefs": [...], "stats": {...}}
    """
    analyzed_pos = analysis_obj.get("purchase_orders", [])
    by_vendor: dict[str, dict[str, Any]] = {}

    for po in analyzed_pos:
        if po.get("recommended_action") != "inquire_vendor":
            continue

        vendor_email = po.get("vendor_email")
        if not vendor_email:
            continue

        if vendor_email not in by_vendor:
            by_vendor[vendor_email] = {
                "vendor": po.get("vendor"),
                "vendor_email": vendor_email,
                "po_ids": set(),
                "pos": [],
                "summary": {"due_pos": 0, "past_due_pos": 0, "unknown_pos": 0},
            }

        state = po.get("state")
        if state == "Due":
            by_vendor[vendor_email]["summary"]["due_pos"] += 1
        elif state == "Past Due":
            by_vendor[vendor_email]["summary"]["past_due_pos"] += 1
        else:
            by_vendor[vendor_email]["summary"]["unknown_pos"] += 1

        by_vendor[vendor_email]["po_ids"].add(po.get("po_id"))

        # Cap lines per PO to avoid huge payloads
        eligible_lines = po.get("eligible_lines_for_inquiry", [])
        capped_lines = eligible_lines[:max_lines_per_po]

        by_vendor[vendor_email]["pos"].append({
            "po_number": po.get("po_number"),
            "po_date": po.get("po_date"),
            "state": po.get("state"),
            "earliest_due_date": po.get("earliest_due_date"),
            "days_since_last_inquiry": po.get("days_since_last_inquiry"),
            "cadence_reason": po.get("cadence_reason"),
            "lines": capped_lines,
        })

    briefs_all = list(by_vendor.values())

    # Convert sets -> lists and apply caps
    for b in briefs_all:
        b["po_ids"] = sorted([x for x in b["po_ids"] if x is not None])
        # Cap POs per vendor
        if len(b["pos"]) > max_pos_per_vendor:
            b["pos"] = b["pos"][:max_pos_per_vendor]
            b["po_ids"] = b["po_ids"][:max_pos_per_vendor]

    briefs = briefs_all[:max_vendors]
    stats = {
        "vendor_count": len(briefs),
        "total_pos": sum(len(b["pos"]) for b in briefs),
        "capped_vendors": len(briefs_all) - len(briefs) if len(briefs_all) > max_vendors else 0,
    }

    return {"briefs": briefs, "stats": stats}


# -----------------------------------------------------------------------------
# SEND + STAMP (deterministic)
# -----------------------------------------------------------------------------

def send_and_stamp(
    *,
    to: str,
    subject: str,
    body: str,
    po_ids: list[int | str],
    send_enabled: bool = True,
) -> dict[str, Any]:
    """
    Deterministic send + stamp operation.

    - If send_enabled=False: returns skipped result, no send, no stamp.
    - If DRY_RUN=true (env): sends in dry-run mode (logged but not delivered), no stamp.
    - Otherwise: sends email, stamps PO headers with today's date.

    Returns: {"send": {...}, "stamp": {...} or None, "skipped": bool}
    """
    if not send_enabled:
        return {
            "send": {"ok": False, "skipped": True, "reason": "SEND_EMAILS=false"},
            "stamp": None,
            "skipped": True,
        }

    send_result = send_email_netsuite(to=to, subject=subject, body=body)

    stamp_result = None
    if send_result.get("ok") and not send_result.get("dry_run", False):
        stamp_result = stamp_last_inq_sent_date_netsuite(po_ids=po_ids)

    return {
        "send": send_result,
        "stamp": stamp_result,
        "skipped": False,
    }


# -----------------------------------------------------------------------------
# AGENT MODE (LLM-based email drafting)
# -----------------------------------------------------------------------------

async def run_agent_mode(
    briefs: list[dict[str, Any]],
    *,
    sleep_sec: float = 1.0,
    send_enabled: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Run LLM agent per vendor to draft and send emails.

    Uses the agents library with Gemini/OpenAI for natural language email drafting.
    """
    # Late imports to avoid loading agent deps if not needed
    from agents import Agent, Runner, function_tool, trace, OpenAIChatCompletionsModel
    from openai import RateLimitError, AsyncOpenAI

    # Load signature from env
    name = os.getenv("EMAIL_SIGNATURE_NAME", "Leon Yang")
    company = os.getenv("EMAIL_SIGNATURE_COMPANY", "Apache Pressure Products")

    # Set up model client
    google_api_key = os.getenv("GOOGLE_API_KEY")
    gemini_base_url = os.getenv("GEMINI_BASE_URL")

    if google_api_key and gemini_base_url:
        client = AsyncOpenAI(base_url=gemini_base_url, api_key=google_api_key)
        model = OpenAIChatCompletionsModel(model="gemini-2.0-flash", openai_client=client)
    else:
        # Fall back to OpenAI if Gemini not configured
        model = "gpt-4o-mini"

    # Capture emails for HTML export
    captured_emails: list[dict[str, Any]] = []

    @function_tool
    def send_and_stamp_tool(to: str, subject: str, body: str, po_ids_json: str) -> str:
        """
        Deterministic: sends email, then stamps last inquiry sent date for provided PO internal IDs.
        po_ids_json must be a JSON array string like: "[626905, 620477]"
        """
        po_ids = json.loads(po_ids_json)
        result = send_and_stamp(
            to=to,
            subject=subject,
            body=body,
            po_ids=po_ids,
            send_enabled=send_enabled,
        )

        # Capture for HTML export
        send_result = result.get("send", {})
        if result.get("skipped"):
            status = "skipped"
        elif send_result.get("dry_run"):
            status = "dry_run"
        elif send_result.get("ok"):
            status = "sent"
        else:
            status = "failed"

        captured_emails.append({
            "to": to,
            "subject": subject,
            "body": body,
            "status": status,
            "po_ids": po_ids,
        })

        return json.dumps(result)

    instructions = (
        f"You are an email writer for vendor PO status inquiries.\n\n"
        f"YOUR ROLE:\n"
        f"- You will receive a vendor brief containing PO data that has already been analyzed.\n"
        f"- Your job is to write a professional, natural-sounding email and send it.\n"
        f"- You have ONE tool: send_and_stamp_tool. Use it to send the email.\n\n"
        f"RULES:\n"
        f"1) Do NOT invent facts. Only use the PO/line data provided in the brief.\n"
        f"2) Write natural, varied emails. Avoid templated/robotic language.\n"
        f"3) Choose tone based on PO state:\n"
        f"   - Due: polite, confirm readiness for upcoming shipment.\n"
        f"   - Past Due: more direct/firm, express urgency.\n"
        f"   - Severity increases with days past due. Orders 30+ days past due risk stockouts.\n"
        f"   - Mixed (some Due, some Past Due): acknowledge both situations.\n"
        f"4) Consolidate all POs for the vendor into ONE email.\n"
        f"5) Always end the email with:\n"
        f"   Best regards,\n"
        f"   {name}\n"
        f"   {company}\n\n"
        f"6) After calling send_and_stamp_tool, do NOT repeat the email content.\n"
        f"   Just confirm the action was taken.\n\n"
        f"TOOL USAGE:\n"
        f"- Call send_and_stamp_tool with: to, subject, body, po_ids_json\n"
        f"- po_ids_json must be a JSON array string, e.g., '[\"628955\", \"628957\"]'\n"
    )

    email_manager = Agent(
        name="PO Email Writer",
        instructions=instructions,
        tools=[send_and_stamp_tool],
    )

    async def run_one_vendor(brief: dict[str, Any], *, max_retries: int = 5) -> dict[str, Any]:
        """Run agent for a single vendor with 429 retry handling."""
        brief_json = json.dumps(brief)
        po_ids_json = json.dumps(brief.get("po_ids", []))
        vendor_email = brief.get("vendor_email", "")

        prompt = (
            "Process exactly ONE vendor brief below.\n"
            "Draft a subject and body, then call send_and_stamp_tool.\n"
            "Do not process any other vendors.\n\n"
            f"vendor_email: {vendor_email}\n"
            f"po_ids_json: {po_ids_json}\n\n"
            f"brief_json:\n{brief_json}\n"
        )

        for attempt in range(max_retries):
            try:
                result = await Runner.run(email_manager, input=prompt, max_turns=10)
                return {"ok": True, "vendor_email": vendor_email, "result": str(result)}
            except RateLimitError as e:
                msg = str(e)
                m = re.search(r"try again in ([0-9.]+)s", msg)
                wait_s = float(m.group(1)) if m else 20.0
                if verbose:
                    print(f"  Rate limited, waiting {wait_s + 1.0:.1f}s...")
                await asyncio.sleep(wait_s + 1.0)

        return {"ok": False, "vendor_email": vendor_email, "error": "Too many 429 retries"}

    # Run vendors with throttling
    results = []
    with trace("PO Vendor Inquiry Run - throttled"):
        for i, brief in enumerate(briefs, start=1):
            vendor_email = brief.get("vendor_email", "?")
            po_count = len(brief.get("pos", []))
            print(f"[{i}/{len(briefs)}] {vendor_email} ({po_count} POs)...", end=" ", flush=True)

            result = await run_one_vendor(brief)
            results.append(result)

            if result.get("ok"):
                print("OK")
            else:
                print(f"FAILED: {result.get('error', 'unknown')}")

            if i < len(briefs):
                await asyncio.sleep(sleep_sec)

    # Enrich captured emails with brief data
    brief_by_email = {b.get("vendor_email"): b for b in briefs}
    for email in captured_emails:
        brief = brief_by_email.get(email.get("to"), {})
        email["vendor"] = brief.get("vendor", "")
        email["po_count"] = len(brief.get("pos", []))
        email["pos"] = brief.get("pos", [])

    return {
        "mode": "agent",
        "processed": len(results),
        "succeeded": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
        "emails": captured_emails,  # For HTML export
    }


# -----------------------------------------------------------------------------
# DETERMINISTIC MODE (no LLM, uses analyzer's build_vendor_inquiries_by_vendor)
# -----------------------------------------------------------------------------

def run_deterministic_mode(
    briefs: list[dict[str, Any]],
    *,
    send_enabled: bool = True,
    sleep_sec: float = 0.5,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Run deterministic email sending without LLM.

    Uses the pre-built email content from analyzer.build_vendor_inquiries_by_vendor().
    """
    import time

    results = []
    emails = []  # For HTML export

    for i, brief in enumerate(briefs, start=1):
        vendor_email = brief.get("vendor_email", "?")
        vendor_name = brief.get("vendor", "")
        po_count = len(brief.get("pos", []))
        po_ids = brief.get("po_ids", [])

        print(f"[{i}/{len(briefs)}] {vendor_email} ({po_count} POs)...", end=" ", flush=True)

        # For deterministic mode, we need to build the email content
        # This is a simplified approach using the brief data
        subject = _build_deterministic_subject(brief)
        body = _build_deterministic_body(brief)

        result = send_and_stamp(
            to=vendor_email,
            subject=subject,
            body=body,
            po_ids=po_ids,
            send_enabled=send_enabled,
        )
        results.append({
            "vendor_email": vendor_email,
            "po_count": po_count,
            **result,
        })

        send_result = result.get("send", {})
        stamp_result = result.get("stamp")

        # Determine status for HTML report
        if result.get("skipped"):
            status = "skipped"
            print("SKIPPED (send disabled)")
        elif send_result.get("dry_run"):
            status = "dry_run"
            print("DRY-RUN")
        elif send_result.get("ok"):
            status = "sent"
            stamp_count = len(stamp_result.get("updated", [])) if stamp_result else 0
            print(f"SENT | stamped {stamp_count} POs")
        else:
            status = "failed"
            print(f"FAILED: {send_result}")

        # Capture email for HTML export
        emails.append({
            "to": vendor_email,
            "vendor": vendor_name,
            "subject": subject,
            "body": body,
            "status": status,
            "po_count": po_count,
            "pos": brief.get("pos", []),
        })

        if i < len(briefs):
            time.sleep(sleep_sec)

    return {
        "mode": "deterministic",
        "processed": len(results),
        "succeeded": sum(1 for r in results if r.get("send", {}).get("ok")),
        "failed": sum(1 for r in results if not r.get("send", {}).get("ok") and not r.get("skipped")),
        "skipped": sum(1 for r in results if r.get("skipped")),
        "results": results,
        "emails": emails,  # For HTML export
    }


def _build_deterministic_subject(brief: dict[str, Any]) -> str:
    """Build a deterministic email subject from brief data."""
    summary = brief.get("summary", {})
    past_due = summary.get("past_due_pos", 0)
    due = summary.get("due_pos", 0)

    if past_due > 0 and due > 0:
        return f"PO Status Update Requested - {past_due} Past Due, {due} Due"
    elif past_due > 0:
        return f"PO Status Update Requested - {past_due} Past Due"
    else:
        return f"PO Status Confirmation - {due} Due Soon"


def _build_deterministic_body(brief: dict[str, Any]) -> str:
    """Build a deterministic email body from brief data."""
    vendor = brief.get("vendor", "(Vendor)")
    name = os.getenv("EMAIL_SIGNATURE_NAME", "Leon Yang")
    company = os.getenv("EMAIL_SIGNATURE_COMPANY", "Apache Pressure Products")

    body = (
        f"Hello {vendor},\n\n"
        "Please provide a status update on the open line(s) for the purchase order(s) below.\n"
        "If items are on shipment, please share the latest ETA and tracking/shipment reference.\n"
        "If items are not yet on shipment, please share the expected ship date.\n\n"
    )

    for p in brief.get("pos", []):
        body += f"{p.get('po_number')} (PO Date: {p.get('po_date')}) | State: {p.get('state')} | Earliest Due: {p.get('earliest_due_date')}\n"
        for ln in p.get("lines", []):
            body += (
                f"  - Line {ln.get('line_no')}: {ln.get('item')} | "
                f"Open Qty: {ln.get('qty_open')} | "
                f"Promise: {ln.get('promise_date')} | "
                f"Due: {ln.get('line_due_date')} | "
                f"On Shipments: {ln.get('qty_on_shipments')}\n"
            )
        body += "\n"

    body += f"Best regards,\n{name}\n{company}\n"
    return body


# -----------------------------------------------------------------------------
# CLI MAIN
# -----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PO Vendor Inquiry CLI - Send status inquiry emails to vendors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py --dry-run                      # Safe test: log what would be sent
  python cli.py --live --max-emails 5          # Send up to 5 vendor emails
  python cli.py --dry-run --no-agent           # Deterministic mode (no LLM)
  python cli.py --test-vendor foo@vendor.com   # Filter to single vendor
  python cli.py --live --sleep 2.0             # 2 second delay between vendors

Environment variables (.env):
  DRY_RUN=true|false         Dry-run mode (overridden by --dry-run/--live)
  SEND_EMAILS=true|false     Master send gate
  MAX_EMAILS=N               Default max vendors
  SLEEP_BETWEEN_VENDORS_SEC  Default delay between vendors
  TEST_VENDOR_EMAIL          Default test vendor filter
""",
    )

    # Mode group
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (log emails but don't actually send)",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Run in live mode (actually send emails and stamp POs)",
    )

    # Processing options
    parser.add_argument(
        "--max-emails",
        type=int,
        default=None,
        help="Maximum number of vendor emails to send (default: from env or 9999)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=None,
        help="Seconds to wait between vendor emails (default: from env or 1.0)",
    )
    parser.add_argument(
        "--test-vendor",
        type=str,
        default=None,
        help="Filter data to single vendor email for testing",
    )

    # Data gathering options
    parser.add_argument(
        "--days-old",
        type=int,
        default=30,
        help="Only look at POs from the last N days (default: 30)",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=500,
        help="Max rows to fetch from NetSuite per page (default: 500)",
    )

    # Mode options
    parser.add_argument(
        "--no-agent",
        action="store_true",
        help="Use deterministic mode (no LLM) instead of agent mode",
    )

    # Output options
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--show-sample",
        action="store_true",
        help="Show a sample email before processing",
    )
    parser.add_argument(
        "--export-html",
        type=str,
        nargs="?",
        const="auto",
        default=None,
        metavar="PATH",
        help="Export full report to HTML file (default: logs/inquiry_report_TIMESTAMP.html)",
    )

    return parser.parse_args()


def main() -> int:
    """Main CLI entrypoint."""
    load_dotenv()
    args = parse_args()

    # Determine dry-run mode
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        dry_run = True
    elif args.live:
        os.environ["DRY_RUN"] = "false"
        dry_run = False
    else:
        dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    # Determine send_enabled (SEND_EMAILS gate)
    send_enabled = os.getenv("SEND_EMAILS", "true").lower() == "true"
    if args.live:
        send_enabled = True

    # Get other settings
    max_emails = args.max_emails or int(os.getenv("MAX_EMAILS", "9999"))
    sleep_sec = args.sleep if args.sleep is not None else float(os.getenv("SLEEP_BETWEEN_VENDORS_SEC", "1.0"))
    test_vendor = args.test_vendor or os.getenv("TEST_VENDOR_EMAIL")

    # Set test vendor in env for datagather to pick up
    if test_vendor:
        os.environ["TEST_VENDOR_EMAIL"] = test_vendor

    # Print header
    mode_str = "DRY-RUN" if dry_run else "LIVE"
    agent_str = "deterministic" if args.no_agent else "agent (LLM)"
    print("=" * 60)
    print(f"PO Vendor Inquiry CLI")
    print(f"Mode: {mode_str} | Engine: {agent_str}")
    print(f"Max emails: {max_emails} | Sleep: {sleep_sec}s")
    if test_vendor:
        print(f"Test vendor filter: {test_vendor}")
    print(f"Send enabled: {send_enabled}")
    print("=" * 60)

    # Phase 1: Data gathering (deterministic)
    print("\n[1/3] Gathering PO data from NetSuite...")
    try:
        dg = datagather(days_old=args.days_old, page_limit=args.page_limit, verbose=args.verbose)
    except Exception as e:
        print(f"ERROR: Failed to gather data: {e}")
        return 1

    print(f"  Found {dg['stats']['po_count']} POs with {dg['stats']['line_count']} lines")

    # Phase 2: Analysis (deterministic)
    print("\n[2/3] Analyzing POs for inquiry eligibility...")
    analysis = analyze(dg["purchase_orders"])
    stats = analysis["stats"]
    print(f"  Normal: {stats['normal_count']} | Due: {stats['due_count']} | Past Due: {stats['past_due_count']}")
    print(f"  Eligible for inquiry: {stats['eligible_for_inquiry_count']}")

    # Build briefs
    briefs_pack = build_vendor_briefs(analysis, max_vendors=max_emails)
    briefs = briefs_pack["briefs"]
    print(f"  Vendors to contact: {len(briefs)}")

    if not briefs:
        print("\nNo vendor inquiries needed. Exiting.")
        return 0

    # Show sample if requested
    if args.show_sample and briefs:
        sample = briefs[0]
        print("\n--- SAMPLE BRIEF ---")
        print(f"Vendor: {sample.get('vendor')} <{sample.get('vendor_email')}>")
        print(f"PO IDs: {sample.get('po_ids')}")
        print(f"Summary: {sample.get('summary')}")
        if args.no_agent:
            print(f"\nSubject: {_build_deterministic_subject(sample)}")
            print(f"\nBody:\n{_build_deterministic_body(sample)}")
        print("--- END SAMPLE ---\n")

    # Phase 3: Send emails
    print(f"\n[3/3] Processing {len(briefs)} vendor(s)...")

    if args.no_agent:
        result = run_deterministic_mode(
            briefs,
            send_enabled=send_enabled,
            sleep_sec=sleep_sec,
            verbose=args.verbose,
        )
    else:
        result = asyncio.run(run_agent_mode(
            briefs,
            sleep_sec=sleep_sec,
            send_enabled=send_enabled,
            verbose=args.verbose,
        ))

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Mode: {result.get('mode')}")
    print(f"Processed: {result.get('processed')}")
    print(f"Succeeded: {result.get('succeeded')}")
    print(f"Failed: {result.get('failed')}")
    if result.get("skipped"):
        print(f"Skipped: {result.get('skipped')}")
    print("=" * 60)

    # Export HTML report if requested
    if args.export_html:
        emails = result.get("emails", [])
        run_info = {
            "mode": result.get("mode"),
            "dry_run": dry_run,
            "max_emails": max_emails,
            "sleep_sec": sleep_sec,
            "send_enabled": send_enabled,
            "test_vendor": test_vendor or "(none)",
            "days_old": args.days_old,
            "no_agent": args.no_agent,
        }

        html = generate_html_report(
            run_info=run_info,
            briefs=briefs,
            emails=emails,
            analysis_stats=stats,
            dg_stats=dg["stats"],
        )

        output_path = None if args.export_html == "auto" else args.export_html
        saved_path = save_html_report(html, output_path)
        print(f"\nHTML report saved to: {saved_path}")

    return 0 if result.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
