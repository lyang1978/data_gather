import json
from emailer.netsuite_sender import send_email_netsuite


def main() -> None:
    result = send_email_netsuite(
        to="leon.yang@apachemfg.com",  # <-- change
        subject="NetSuite RESTlet email test (module)",
        body="Hello! This is a test email sent from NetSuite via RESTlet (netsuite_sender.py).",
        # author=123,  # optional: internal employee id
    )

    print("Result:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
