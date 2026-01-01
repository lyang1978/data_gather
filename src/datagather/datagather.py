from __future__ import annotations

from datetime import datetime
from typing import Any

from .netsuite_client import run_suiteql_paged
from .queries import open_po_lines_query
from .transform import group_lines_by_po

import os

def datagather(
    *,
    days_old: int = 30,
    page_limit: int = 500,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Public entry point for DataGather.

    Returns a JSON-serializable dict:
      {
        "purchase_orders": [ ... ],
        "stats": { ... }
      }
    """
    vendor_email = os.getenv("TEST_VENDOR_EMAIL")  # TESTING ONLY REMOVE WHEN DONE TESTING

    query = open_po_lines_query(days_old=days_old, vendor_email=vendor_email)

    rows = run_suiteql_paged(query, limit=page_limit, verbose=verbose)
    purchase_orders = group_lines_by_po(rows)

    # Optional: quick counters for missing fields
    missing_due = sum(
        1 for r in rows if not r.get("line_due_date")
    )
    missing_vendor_email = sum(
        1 for r in rows if not r.get("vendor_email")
    )

    return {
        "purchase_orders": purchase_orders,
        "stats": {
            "po_count": len(purchase_orders),
            "line_count": len(rows),
            "days_old_filter": days_old,
            "page_limit": page_limit,
            "missing_due_date_lines": missing_due,
            "missing_vendor_email_lines": missing_vendor_email,
            "run_timestamp_local": datetime.now().isoformat(timespec="seconds"),
        },
    }
