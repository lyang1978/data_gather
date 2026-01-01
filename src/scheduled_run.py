"""
Scheduled PO Vendor Inquiry Runner

This script is designed to be run by Windows Task Scheduler (or any scheduler).
It runs the full pipeline: data gather -> analyze -> LLM email writing -> send/stamp.

Configuration via environment variables (.env file):
    DRY_RUN=true|false          - If true, emails are logged but not sent (default: true)
    SEND_EMAILS=true|false      - Master gate for sending (default: false)
    MAX_EMAILS=N                - Max vendors to email per run (default: 9999)
    SLEEP_BETWEEN_VENDORS_SEC=N - Delay between vendors (default: 1.0)

Usage:
    # From project root with venv activated:
    python src/scheduled_run.py

    # Or directly with full path:
    D:\\OneDrive\\Projects\\data_gather\\.venv\\Scripts\\python.exe D:\\OneDrive\\Projects\\data_gather\\src\\scheduled_run.py

Exit codes:
    0 - Success (all emails sent/logged)
    1 - Partial failure (some emails failed)
    2 - Fatal error (pipeline failed)
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure src directory is in path for imports
src_dir = Path(__file__).parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from dotenv import load_dotenv

from datagather.datagather import datagather
from analyzer.analyzer import analyze
from po_email_agent_runner import create_email_agent, run_agent_for_one_vendor, build_vendor_briefs


def setup_logging() -> Path:
    """Setup log file for this run. Returns log file path."""
    logs_dir = src_dir.parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"scheduled_run_{timestamp}.log"

    return log_path


def log(msg: str, log_file: Path | None = None) -> None:
    """Print message and optionally write to log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)

    if log_file:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


async def run_scheduled_job() -> int:
    """
    Run the scheduled PO vendor inquiry job.

    Returns exit code: 0=success, 1=partial failure, 2=fatal error
    """
    load_dotenv()

    log_file = setup_logging()
    log(f"Starting scheduled PO vendor inquiry run", log_file)
    log(f"Log file: {log_file}", log_file)

    # Read configuration
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    send_enabled = os.getenv("SEND_EMAILS", "false").lower() == "true"
    max_vendors = int(os.getenv("MAX_EMAILS", "9999"))
    sleep_sec = float(os.getenv("SLEEP_BETWEEN_VENDORS_SEC", "1.0"))

    log(f"Configuration:", log_file)
    log(f"  DRY_RUN={dry_run}", log_file)
    log(f"  SEND_EMAILS={send_enabled}", log_file)
    log(f"  MAX_EMAILS={max_vendors}", log_file)
    log(f"  SLEEP_BETWEEN_VENDORS_SEC={sleep_sec}", log_file)

    try:
        # 1) Gather data from NetSuite
        log("Step 1/4: Gathering PO data from NetSuite...", log_file)
        dg = datagather(days_old=30, page_limit=500, verbose=False)
        stats = dg.get("stats", {})
        log(f"  Found {stats.get('po_count', 0)} POs with {stats.get('line_count', 0)} lines", log_file)

        # 2) Analyze POs
        log("Step 2/4: Analyzing POs for inquiry eligibility...", log_file)
        analysis = analyze(dg["purchase_orders"])
        analysis_stats = analysis.get("stats", {})
        log(f"  Normal: {analysis_stats.get('normal_count', 0)}", log_file)
        log(f"  Due: {analysis_stats.get('due_count', 0)}", log_file)
        log(f"  Past Due: {analysis_stats.get('past_due_count', 0)}", log_file)
        log(f"  Eligible for inquiry: {analysis_stats.get('eligible_for_inquiry_count', 0)}", log_file)

        # 3) Build vendor briefs
        log("Step 3/4: Building vendor briefs...", log_file)
        briefs_pack = build_vendor_briefs(analysis, max_vendors=max_vendors)
        briefs = briefs_pack.get("briefs", [])
        brief_stats = briefs_pack.get("stats", {})
        log(f"  Vendors to contact: {brief_stats.get('vendor_count', 0)}", log_file)
        log(f"  Total POs: {brief_stats.get('total_pos', 0)}", log_file)

        if not briefs:
            log("No vendors require inquiry emails. Exiting.", log_file)
            return 0

        # 4) Process vendors with LLM agent
        log(f"Step 4/4: Processing {len(briefs)} vendor(s) with LLM agent...", log_file)

        captured_emails: list[dict] = []
        agent = create_email_agent(send_enabled=send_enabled, captured_emails=captured_emails)

        succeeded = 0
        failed = 0

        for i, brief in enumerate(briefs, start=1):
            vendor_email = brief.get("vendor_email", "?")
            po_count = len(brief.get("pos", []))

            log(f"  [{i}/{len(briefs)}] {vendor_email} ({po_count} POs)...", log_file)

            result = await run_agent_for_one_vendor(agent, brief, verbose=False)

            if result.get("ok"):
                succeeded += 1
                log(f"    OK", log_file)
            else:
                failed += 1
                log(f"    FAILED: {result.get('error', 'unknown')}", log_file)

            if i < len(briefs):
                await asyncio.sleep(sleep_sec)

        # Summary
        log("", log_file)
        log("=" * 60, log_file)
        log("RUN SUMMARY", log_file)
        log("=" * 60, log_file)
        log(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}", log_file)
        log(f"Vendors processed: {len(briefs)}", log_file)
        log(f"Succeeded: {succeeded}", log_file)
        log(f"Failed: {failed}", log_file)

        # Log email details
        for email in captured_emails:
            status = email.get("status", "unknown")
            to = email.get("to", "?")
            subject = email.get("subject", "(no subject)")
            log(f"  [{status.upper()}] {to}: {subject}", log_file)

        log("=" * 60, log_file)
        log(f"Log saved to: {log_file}", log_file)

        # Save captured emails to JSONL
        if captured_emails:
            jsonl_path = src_dir.parent / "logs" / "sent_emails.jsonl"
            with open(jsonl_path, "a", encoding="utf-8") as f:
                for email in captured_emails:
                    record = {
                        "timestamp": datetime.now().isoformat(),
                        "dry_run": dry_run,
                        **email,
                    }
                    f.write(json.dumps(record) + "\n")
            log(f"Email records appended to: {jsonl_path}", log_file)

        return 1 if failed > 0 else 0

    except Exception as e:
        log(f"FATAL ERROR: {e}", log_file)
        import traceback
        log(traceback.format_exc(), log_file)
        return 2


def main() -> int:
    """Main entry point."""
    return asyncio.run(run_scheduled_job())


if __name__ == "__main__":
    sys.exit(main())
