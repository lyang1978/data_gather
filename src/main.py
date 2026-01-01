import os
import json

from datagather.datagather import datagather
from analyzer.analyzer import analyze, build_vendor_inquiries_by_vendor
from emailer.netsuite_sender import send_email_netsuite
from dotenv import load_dotenv

def main() -> None:
    load_dotenv()
    # print(os.getenv("TEST_VENDOR_EMAIL"))
    # Safety knobs (set these in .env if you want)
    max_emails = int(os.getenv("MAX_EMAILS", "2"))          # default: only send 2 vendors
    send_enabled = os.getenv("SEND_EMAILS", "false").lower() == "true"  # default: no send

    dg = datagather(days_old=30, page_limit=500, verbose=True)
    analysis = analyze(dg["purchase_orders"])

    pack = build_vendor_inquiries_by_vendor(analysis["purchase_orders"])
    print("Vendor inquiry stats:", pack["stats"])

    inquiries = pack["inquiries"]
    if not inquiries:
        print("No vendor inquiries to send.")
        return
    
    print("Target vendor emails:", sorted({x["vendor_email"] for x in inquiries}))
    # Always show one sample so you can sanity-check content
    for i in inquiries:
        sample = i
        print("\n--- SAMPLE VENDOR EMAIL ---")
        print("To:", sample["vendor_email"])
        print("Subject:", sample["subject"])
        print(sample["body"])

    if not send_enabled:
        print("\nSEND_EMAILS=false, not sending. (Set SEND_EMAILS=true in .env to enable)")
        return

    # Send loop (bounded)
    to_send = inquiries[:max_emails]
    print(f"\nSending {len(to_send)} vendor email(s) (max_emails={max_emails})...")

    sent = 0
    failed = 0

    for i, msg in enumerate(to_send, start=1):
        to_addr = msg["vendor_email"]
        subject = msg["subject"]
        body = msg["body"]

        try:
            result = send_email_netsuite(to=to_addr, subject=subject, body=body)
            print(f"[{i}/{len(to_send)}] ✅ Sent to {to_addr} | ok={result.get('ok')} http={result.get('http')}")
            sent += 1
        except Exception as e:
            print(f"[{i}/{len(to_send)}] ❌ Failed to send to {to_addr}: {e}")
            failed += 1

    print("\n--- SEND SUMMARY ---")
    print(json.dumps({"attempted": len(to_send), "sent": sent, "failed": failed}, indent=2))


if __name__ == "__main__":
    main()
