from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


def _to_int(x: Any) -> int:
    if x is None or x == "":
        return 0
    try:
        # NetSuite often returns numbers as strings
        return int(float(x))
    except Exception:
        return 0


def _parse_mmddyyyy(d: Any) -> date | None:
    if not d:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    s = str(d).strip()
    try:
        return datetime.strptime(s, "%m/%d/%Y").date()
    except ValueError:
        # Some accounts may return ISO format; accept it too
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None


def _po_state(earliest_due: date, today: date) -> str:
    # Your rules:
    # Normal: due > today + 14
    # Due: today <= due <= today + 14
    # Past Due: due < today
    if earliest_due < today:
        return "Past Due"
    if earliest_due <= (today + timedelta(days=14)):
        return "Due"
    return "Normal"


def analyze(
    purchase_orders: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """
    Analyzer tool.

    Input: purchase_orders from datagather()["purchase_orders"]
    Output: JSON-serializable dict with per-PO state + recommended action.
    """
    today = as_of or date.today()
    
    should_inquire = False
    cadence_reason = None
    days_since_last_inq = None

    analyzed: list[dict[str, Any]] = []
    stats = {
        "as_of": today.isoformat(),
        "po_count": 0,
        "line_count": 0,
        "normal_count": 0,
        "due_count": 0,
        "past_due_count": 0,
        "needs_buyer_data_count": 0,
        "eligible_for_inquiry_count": 0,
    }

    for po in purchase_orders:
        lines = po.get("lines", [])
        stats["po_count"] += 1
        stats["line_count"] += len(lines)
        last_sent = _parse_mmddyyyy(po.get("last_inq_sent_date"))
        # Only consider open lines for state. (Your datagather already filters qty_open > 0,
        # but we keep this defensive.)
        open_lines = [ln for ln in lines if _to_int(ln.get("qty_open")) > 0]

        # actionable lines = open AND NOT fully shipped (on shipments < qty ordered)
        actionable_lines = []
        for ln in open_lines:
            qty_ordered = _to_int(ln.get("qty_ordered"))
            qty_on_shipments = _to_int(ln.get("qty_on_shipments"))

            # If shipped in full (or over), no vendor inquiry needed for this line
            if qty_ordered > 0 and qty_on_shipments >= qty_ordered:
                continue

            actionable_lines.append(ln)



        # Collect due dates among open lines (earliest due drives PO state)
        parsed_due_dates = []
        missing_due_lines = []

        for ln in actionable_lines:
            due = _parse_mmddyyyy(ln.get("line_due_date"))
            if due is None:
                missing_due_lines.append(
                    {"line_no": ln.get("line_no"), "item": ln.get("item")}
                )
            else:
                parsed_due_dates.append(due)

        # If we can't determine any due date, we can't classify reliably
        if not parsed_due_dates:
            stats["needs_buyer_data_count"] += 1
            analyzed.append(
                {
                    "po_id": po.get("po_id"),
                    "po_number": po.get("po_number"),
                    "po_date": po.get("po_date"), 
                    "last_inq_sent_date" : po.get("last_inq_sent_date"),
                    "days_since_last_inquiry": days_since_last_inq,

                    "vendor": po.get("vendor"),
                    "vendor_email": po.get("vendor_email"),
                    "last_inq_sent_date" : po.get("last_inq_sent_date"),
                    "state": "Unknown",
                    "earliest_due_date": None,
                    "open_line_count": len(actionable_lines),
                    "missing_due_date_lines": missing_due_lines,
                    "recommended_action": "notify_buyer_missing_due_dates",
                    "eligible_lines_for_inquiry": [],
                }
            )
            continue

        earliest_due = min(parsed_due_dates)
        state = _po_state(earliest_due, today)

        if state == "Normal":
            stats["normal_count"] += 1
        elif state == "Due":
            stats["due_count"] += 1
        else:
            stats["past_due_count"] += 1

        # Eligible lines for inquiry: open + have due_date + are Due or Past Due (<= today+14)
        eligible_lines = []
        for ln in actionable_lines:
            due = _parse_mmddyyyy(ln.get("line_due_date"))
            if due is None:
                continue

            # NEW RULE: if shipped in full (on shipments >= qty ordered), skip inquiry
            qty_on_shipments = _to_int(ln.get("qty_on_shipments"))
            qty_ordered = _to_int(ln.get("qty_ordered"))
            if qty_on_shipments >= qty_ordered and qty_ordered > 0:
                continue

            if due <= (today + timedelta(days=14)):
                eligible_lines.append(ln)
        

        

        if last_sent:
            days_since_last_inq = (today - last_sent).days
            # If bad data (future date), don't inquire
            if days_since_last_inq < 0:
                days_since_last_inq = None

        if eligible_lines:
            if state == "Due":
                # Send once per due-window (starts at earliest_due - 14)
                due_window_start = earliest_due - timedelta(days=14)
                if (last_sent is None) or (last_sent < due_window_start):
                    should_inquire = True
                    cadence_reason = "due_first_touch"
                else:
                    should_inquire = False
                    cadence_reason = "due_already_touched"
            elif state == "Past Due":
                # Weekly cadence once late
                if (last_sent is None) or ((today - last_sent).days >= 7):
                    should_inquire = True
                    cadence_reason = "past_due_weekly"
                else:
                    should_inquire = False
                    cadence_reason = "past_due_waiting_week"


        recommended_action = "none"
        if missing_due_lines:
            # Even if inquiry is possible, missing due dates are a buyer problem worth flagging
            recommended_action = "notify_buyer_missing_due_dates"
            stats["needs_buyer_data_count"] += 1

        if eligible_lines:
            # If it's due/past-due (or within 14 days), we should inquire vendor
            recommended_action = "inquire_vendor"
            stats["eligible_for_inquiry_count"] += 1

        analyzed.append(
            {
                "po_id": po.get("po_id"),
                "po_number": po.get("po_number"),
                "po_date": po.get("po_date"), 
                "last_inq_sent_date" : po.get("last_inq_sent_date"),
                "vendor": po.get("vendor"),
                "vendor_email": po.get("vendor_email"),
                "last_inq_sent_date" : po.get("last_inq_sent_date"),
                "days_since_last_inquiry": days_since_last_inq,
                "state": state,
                "earliest_due_date": earliest_due.isoformat(),
                "open_line_count": len(actionable_lines),
                "missing_due_date_lines": missing_due_lines,
                "recommended_action": recommended_action,
                "eligible_lines_for_inquiry": eligible_lines,
            }
        )

    return {"purchase_orders": analyzed, "stats": stats}


def _to_int_safe(x: Any) -> int:
    if x is None or x == "":
        return 0
    try:
        return int(float(x))
    except Exception:
        return 0


def build_vendor_inquiries(
    analyzed_purchase_orders: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """
    Build deterministic vendor inquiry payloads from Analyzer output.

    Only includes POs where recommended_action == 'inquire_vendor'.
    If vendor_email is missing, it will skip the inquiry and instead count it as 'missing_vendor_email'.
    """
    today = as_of or date.today()

    inquiries: list[dict[str, Any]] = []
    stats = {
        "as_of": today.isoformat(),
        "inquiry_count": 0,
        "skipped_missing_vendor_email": 0,
        "total_eligible_lines": 0,
        "due_inquiries": 0,
        "past_due_inquiries": 0,
    }

    for po in analyzed_purchase_orders:
        if po.get("recommended_action") != "inquire_vendor":
            continue

        vendor_email = po.get("vendor_email")
        if not vendor_email:
            stats["skipped_missing_vendor_email"] += 1
            continue

        po_number = po.get("po_number")
        vendor = po.get("vendor")
        state = po.get("state")
        earliest_due = po.get("earliest_due_date")
        eligible_lines = po.get("eligible_lines_for_inquiry", [])

        # Build structured line bullets + decide what to ask for
        line_summaries = []
        ask_tracking = False  # if any line has qty_on_shipments > 0

        for ln in eligible_lines:
            qty_open = _to_int_safe(ln.get("qty_open"))
            qty_on_shipments = _to_int_safe(ln.get("qty_on_shipments"))

            if qty_on_shipments > 0:
                ask_tracking = True

            line_summaries.append(
                {
                    "line_no": ln.get("line_no"),
                    "item": ln.get("item"),
                    "promise_date": ln.get("promise_date"),
                    "due_date": ln.get("line_due_date"),
                    "qty_open": qty_open,
                    "qty_on_shipments": qty_on_shipments,
                }
            )

        stats["total_eligible_lines"] += len(line_summaries)

        if state == "Past Due":
            stats["past_due_inquiries"] += 1
            subject = f"PO {po_number} – Past Due – Status Update Requested"
            opener = (
                f"Hello {vendor},\n\n"
                f"Our records show PO {po_number} is past due (earliest due date: {earliest_due}). "
                f"Please provide an update on the open line(s) below:\n"
            )
        else:
            # Includes "Due" and any other state where Analyzer still chose to inquire
            stats["due_inquiries"] += 1
            subject = f"PO {po_number} – Upcoming Due Date – Status Confirmation"
            opener = (
                f"Hello {vendor},\n\n"
                f"Our records show PO {po_number} is coming due soon (earliest due date: {earliest_due}). "
                f"Please confirm status on the open line(s) below:\n"
            )

        bullets = ""
        for ls in line_summaries:
            bullets += (
                f"- Line {ls['line_no']}: {ls['item']} | "
                f"Open Qty: {ls['qty_open']} | "
                f"Promise: {ls.get('promise_date')} | "
                f"Due: {ls.get('due_date')} | "
                f"On Shipments: {ls['qty_on_shipments']}\n"
            )

        if ask_tracking:
            ask = (
                "\nFor any items already on shipment, please share the latest ETA and tracking / shipment reference.\n"
                "For any items not yet on shipment, please share the expected ship date.\n"
            )
        else:
            ask = "\nPlease share the expected ship date (or confirm shipment is on schedule).\n"

        close = (
            "\nThank you,\n"
            "Purchasing\n"
        )

        body = opener + "\n" + bullets + ask + close

        inquiries.append(
            {
                "po_id": po.get("po_id"),
                "po_number": po_number,
                "vendor": vendor,
                "vendor_email": vendor_email,
                "state": state,
                "earliest_due_date": earliest_due,
                "subject": subject,
                "body": body,
                "lines": line_summaries,
            }
        )

    stats["inquiry_count"] = len(inquiries)
    return {"inquiries": inquiries, "stats": stats}


def build_vendor_inquiries_by_vendor(
    analyzed_purchase_orders: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """
    Build 1 inquiry email per vendor_email, combining all POs where
    recommended_action == 'inquire_vendor'.
    """
    today = as_of or date.today()

    # vendor_email -> bucket
    buckets: dict[str, dict[str, Any]] = {}

    stats = {
        "as_of": today.isoformat(),
        "vendor_inquiry_count": 0,
        "skipped_missing_vendor_email": 0,
        "total_pos_included": 0,
        "total_lines_included": 0,
        "due_pos": 0,
        "past_due_pos": 0,
    }

    for po in analyzed_purchase_orders:
        if po.get("recommended_action") != "inquire_vendor":
            continue

        vendor_email = po.get("vendor_email")
        if not vendor_email:
            stats["skipped_missing_vendor_email"] += 1
            continue

        vendor = po.get("vendor") or "(Vendor)"
        state = po.get("state")
        earliest_due = po.get("earliest_due_date")
        eligible_lines = po.get("eligible_lines_for_inquiry", [])
        po_number = po.get("po_number")

        if vendor_email not in buckets:
            buckets[vendor_email] = {
                "vendor": vendor,
                "vendor_email": vendor_email,
                "pos": [],
            }

        # Keep a per-PO payload
        line_summaries = []
        any_on_shipments = False
        for ln in eligible_lines:
            qty_open = _to_int_safe(ln.get("qty_open"))
            qty_on_shipments = _to_int_safe(ln.get("qty_on_shipments"))
            if qty_on_shipments > 0:
                any_on_shipments = True

            line_summaries.append(
                {
                    "line_no": ln.get("line_no"),
                    "item": ln.get("item"),
                    "promise_date": ln.get("promise_date"),
                    "due_date": ln.get("line_due_date"),
                    "qty_open": qty_open,
                    "qty_on_shipments": qty_on_shipments,
                }
            )

        buckets[vendor_email]["pos"].append(
            {
                "po_id": po.get("po_id"),
                "po_number": po_number,
                "po_date": po.get("po_date"), 
                "state": state,
                "earliest_due_date": earliest_due,
                "lines": line_summaries,
                "any_on_shipments": any_on_shipments,
            }
        )

    inquiries: list[dict[str, Any]] = []

    for vendor_email, b in buckets.items():
        vendor = b["vendor"]
        pos_list = b["pos"]
        po_ids = sorted(
            {p.get("po_id") for p in pos_list if p.get("po_id") is not None}
        )
        
        # Sort: Past Due first, then Due, then by earliest due date
        def _sort_key(p: dict[str, Any]) -> tuple:
            state = p.get("state") or ""
            rank = 0
            if state == "Past Due":
                rank = 0
            elif state == "Due":
                rank = 1
            else:
                rank = 2
            # earliest_due_date is ISO string or None; None goes last
            ed = p.get("earliest_due_date") or "9999-12-31"
            return (rank, ed, p.get("po_number") or "")

        pos_list.sort(key=_sort_key)

        past_due_count = sum(1 for p in pos_list if p.get("state") == "Past Due")
        due_count = sum(1 for p in pos_list if p.get("state") == "Due")

        stats["total_pos_included"] += len(pos_list)
        stats["past_due_pos"] += past_due_count
        stats["due_pos"] += due_count

        total_lines = sum(len(p.get("lines", [])) for p in pos_list)
        stats["total_lines_included"] += total_lines

        # Subject: one per vendor
        if past_due_count > 0 and due_count > 0:
            subject = f"PO Status Update Requested – {past_due_count} Past Due, {due_count} Due"
        elif past_due_count > 0:
            subject = f"PO Status Update Requested – {past_due_count} Past Due"
        else:
            subject = f"PO Status Confirmation – {due_count} Due Soon"

        # Body
        header = (
            f"Hello {vendor},\n\n"
            "Please provide a status update on the open line(s) for the purchase order(s) below.\n"
            "If items are on shipment, please share the latest ETA and tracking/shipment reference.\n"
            "If items are not yet on shipment, please share the expected ship date.\n\n"
        )

        body = header

        for p in pos_list:
          body += f"{p['po_number']} (PO Date: {p.get('po_date')}) | State: {p.get('state')} | Earliest Due: {p.get('earliest_due_date')}\n"
          for ln in p.get("lines", []):
                body += (
                    f"- Line {ln.get('line_no')}: {ln.get('item')} | "
                    f"Open Qty: {ln.get('qty_open')} | "
                    f"Promise: {ln.get('promise_date')} | "
                    f"Due: {ln.get('due_date')} | "
                    f"On Shipments: {ln.get('qty_on_shipments')}"
                )
                body += "\n"

        body += "Thank you,\nPurchasing\n"

        inquiries.append(
            {
                "vendor": vendor,
                "vendor_email": vendor_email,
                "subject": subject,
                "body": body,
                "po_ids" : po_ids,
                "pos": pos_list,  # structured details for downstream tools/logging
                
            }
        )

    stats["vendor_inquiry_count"] = len(inquiries)
    return {"inquiries": inquiries, "stats": stats}