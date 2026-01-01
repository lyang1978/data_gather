from collections import OrderedDict
from typing import Any

def group_lines_by_po(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pos: "OrderedDict[str, dict[str, Any]]" = OrderedDict()

    for r in rows:
        po_id = str(r.get("po_id"))

        if po_id not in pos:
            pos[po_id] = {
                "po_id": po_id,
                "po_number": r.get("po_number"),
                "po_date" : r.get("po_date"),
                "vendor": r.get("vendor"),
                "vendor_email": r.get("vendor_email"),
                "last_inq_sent_date" : r.get("last_inq_sent_date"),
                "lines": [],
            }

        line = {
            "line_no": r.get("line_no"),
            "item": r.get("item"),
            "promise_date": r.get("promise_date"),
            "line_due_date": r.get("line_due_date"),
            "qty_ordered": r.get("qty_ordered"),
            "qty_received": r.get("qty_received"),
            "qty_open": r.get("qty_open"),
            "qty_on_shipments": r.get("qty_on_shipments"),
        }

        pos[po_id]["lines"].append(line)

    return list(pos.values())
