"""
PO Email Agent Runner

Workflow:
1. DETERMINISTIC: Pull data from NetSuite, analyze POs, build vendor briefs
2. LLM: Write emails with natural tone (one per vendor)
3. DETERMINISTIC: Send email via NetSuite RESTlet, stamp PO headers

The LLM agent ONLY writes the email - it does not have access to data-gathering tools.
All data is provided to the agent via the vendor brief in the prompt.
"""

import asyncio
import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from agents import Agent, Runner, function_tool, trace
from openai import RateLimitError

from datagather.datagather import datagather
from analyzer.analyzer import analyze
from emailer.netsuite_sender import send_email_netsuite
from emailer.netsuite_stamper import stamp_last_inq_sent_date_netsuite


load_dotenv()


# -----------------------------------------------------------------------------
# DETERMINISTIC SEND + STAMP
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

    return {"send": send_result, "stamp": stamp_result, "skipped": False}


# -----------------------------------------------------------------------------
# AGENT FACTORY
# -----------------------------------------------------------------------------

def create_email_agent(
    *,
    send_enabled: bool = True,
    captured_emails: list[dict[str, Any]] | None = None,
) -> Agent:
    """
    Create an email-writing agent with send_and_stamp_tool.

    Args:
        send_enabled: Whether to actually send emails (respects SEND_EMAILS gate)
        captured_emails: Optional list to capture sent emails for reporting

    Returns:
        Agent configured with send_and_stamp_tool only
    """
    # Read signature fresh each time
    name = os.getenv("EMAIL_SIGNATURE_NAME", "Leon Yang")
    company = os.getenv("EMAIL_SIGNATURE_COMPANY", "Apache Pressure Products")

    # Create tool with closure over send_enabled and captured_emails
    @function_tool
    def send_and_stamp_tool(to: str, subject: str, body: str, po_ids_json: str) -> str:
        """
        Send email and stamp PO headers with inquiry date.

        Args:
            to: Recipient email address
            subject: Email subject line
            body: Email body text
            po_ids_json: JSON array string of PO internal IDs, e.g., '["628955", "628957"]'

        Returns:
            JSON string with send and stamp results
        """
        po_ids = json.loads(po_ids_json)
        result = send_and_stamp(
            to=to,
            subject=subject,
            body=body,
            po_ids=po_ids,
            send_enabled=send_enabled,
        )

        # Capture email for reporting if list provided
        if captured_emails is not None:
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
        f"- You receive a vendor brief with PO data that has already been analyzed.\n"
        f"- Write a professional, natural-sounding email and send it using send_and_stamp_tool.\n\n"
        f"RULES:\n"
        f"1) Only use facts from the brief. Do NOT invent data.\n"
        f"2) Write natural, varied emails. Avoid robotic/templated language.\n"
        f"3) Tone based on PO state:\n"
        f"   - Due: polite, confirm shipment readiness.\n"
        f"   - Past Due: direct/firm, express urgency.\n"
        f"   - 30+ days past due: risk of stockouts, higher urgency.\n"
        f"   - Mixed: acknowledge both situations.\n"
        f"4) ONE email per vendor, consolidating all their POs.\n"
        f"5) End with:\n"
        f"   Best regards,\n"
        f"   {name}\n"
        f"   {company}\n\n"
        f"6) After calling send_and_stamp_tool, just confirm - don't repeat email content.\n\n"
        f"TOOL: send_and_stamp_tool(to, subject, body, po_ids_json)\n"
        f"  - po_ids_json is a JSON array string: '[\"628955\", \"628957\"]'\n"
    )

    return Agent(
        name="PO Email Writer",
        instructions=instructions,
        tools=[send_and_stamp_tool],
    )


# -----------------------------------------------------------------------------
# RUN AGENT FOR ONE VENDOR
# -----------------------------------------------------------------------------

async def run_agent_for_one_vendor(
    agent: Agent,
    brief: dict[str, Any],
    *,
    max_retries: int = 5,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Run the email agent for a single vendor brief.

    Retries on 429 rate limit errors with server-provided wait time.
    """
    brief_json = json.dumps(brief)
    po_ids_json = json.dumps(brief.get("po_ids", []))
    vendor_email = brief.get("vendor_email", "")

    prompt = (
        "Write and send ONE email for the vendor brief below.\n\n"
        f"vendor_email: {vendor_email}\n"
        f"po_ids_json: {po_ids_json}\n\n"
        f"brief:\n{brief_json}\n"
    )

    for attempt in range(max_retries):
        try:
            result = await Runner.run(agent, input=prompt, max_turns=10)
            return {"ok": True, "vendor_email": vendor_email, "result": str(result)}
        except RateLimitError as e:
            msg = str(e)
            m = re.search(r"try again in ([0-9.]+)s", msg)
            wait_s = float(m.group(1)) if m else 20.0
            if verbose:
                print(f"  Rate limited, waiting {wait_s + 1.0:.1f}s...")
            await asyncio.sleep(wait_s + 1.0)

    return {"ok": False, "vendor_email": vendor_email, "error": "Too many 429 retries"}


def build_vendor_briefs(
    analysis_obj: dict,
    *,
    max_vendors: int = 50,
    max_pos_per_vendor: int = 20,
    max_lines_per_po: int = 50,
) -> dict:
    """
    Build vendor briefs from analyzer output (dict, not JSON string).

    Only includes POs where recommended_action == 'inquire_vendor'.
    Caps briefs to avoid excessive context in LLM calls.

    Returns: {"briefs": [...], "stats": {...}}
    """
    analyzed_pos = analysis_obj.get("purchase_orders", [])
    by_vendor = {}

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
# MAIN ENTRY POINT
# -----------------------------------------------------------------------------

async def main() -> None:
    load_dotenv()

    max_vendors = int(os.getenv("MAX_EMAILS", "9999"))
    sleep_s = float(os.getenv("SLEEP_BETWEEN_VENDORS_SEC", "1.0"))
    send_enabled = os.getenv("SEND_EMAILS", "false").lower() == "true"

    # 1) Deterministic pipeline (no LLM) to get vendor briefs
    print("Gathering PO data from NetSuite...")
    dg = datagather(days_old=30, page_limit=500, verbose=False)
    analysis = analyze(dg["purchase_orders"])
    briefs_pack = build_vendor_briefs(analysis, max_vendors=max_vendors)
    briefs = briefs_pack.get("briefs", [])

    if not briefs:
        print("No vendors require inquiry emails.")
        return

    print(f"Vendors to process: {len(briefs)} | sleep={sleep_s}s | send_enabled={send_enabled}")

    # 2) Create agent with factory (captures send_enabled via closure)
    captured_emails: list[dict[str, Any]] = []
    agent = create_email_agent(send_enabled=send_enabled, captured_emails=captured_emails)

    # 3) LLM per vendor (throttled)
    with trace("PO Vendor Inquiry Run - throttled"):
        for i, brief in enumerate(briefs, start=1):
            print(f"\n--- Vendor {i}/{len(briefs)}: {brief.get('vendor_email')} ---")
            result = await run_agent_for_one_vendor(agent, brief, verbose=True)
            if result.get("ok"):
                print(f"  Done.")
            else:
                print(f"  Failed: {result.get('error')}")
            await asyncio.sleep(sleep_s)

    # 4) Summary
    print(f"\n--- SUMMARY ---")
    print(f"Total vendors processed: {len(briefs)}")
    print(f"Emails captured: {len(captured_emails)}")
    for email in captured_emails:
        print(f"  {email['status']}: {email['to']}")


if __name__ == "__main__":
    asyncio.run(main())
