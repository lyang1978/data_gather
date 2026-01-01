import json
from emailer.netsuite_stamper import stamp_last_inq_sent_date_netsuite

def main() -> None:
    # Use ONE real Purchase Order *internal id* first
    po_ids = [628955]  # <-- change this

    result = stamp_last_inq_sent_date_netsuite(
        po_ids=po_ids,
        sent_date="2025-12-26",  # optional; omit to use today's date
    )

    print("Stamp result:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()

