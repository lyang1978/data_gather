def open_po_lines_query(days_old: int = 30, vendor_email: str | None = None) -> str:

    vendor_clause = ""
    if vendor_email:
        safe_email = vendor_email.replace("'", "''")  # escape single quotes for SQL
        vendor_clause = f"\n            AND v.email = '{safe_email}'"
        
    print(vendor_clause)
    return f"""
        SELECT
            t.id AS po_id,
            t.tranid AS po_number,
            t.trandate AS po_date,
            t.custbody_last_inq_sent_date_ AS last_inq_sent_date,

            BUILTIN.DF(t.entity) AS vendor,
            v.email AS vendor_email,

            tl.linesequencenumber AS line_no,
            BUILTIN.DF(tl.item) AS item,

            tl.custcol_atlas_wd_promise_date AS promise_date,
            tl.custcol1 AS line_due_date,

            tl.quantity AS qty_ordered,
            tl.quantityshiprecv AS qty_received,
            (tl.quantity - tl.quantityshiprecv) AS qty_open,
            COALESCE(tl.quantityonshipments, 0) AS qty_on_shipments

        FROM transaction t
        JOIN transactionLine tl
            ON tl.transaction = t.id

        LEFT JOIN Vendor v
            ON v.id = t.entity

        WHERE t.type = 'PurchOrd'
            AND t.trandate < (SYSDATE - {days_old})
            AND t.status NOT IN ('G', 'H')
            AND tl.mainline = 'F'
            AND tl.item IS NOT NULL
            AND (tl.quantity - tl.quantityshiprecv) > 0
            AND tl.isclosed = 'F'
            

        ORDER BY t.id DESC, tl.linesequencenumber
    """
