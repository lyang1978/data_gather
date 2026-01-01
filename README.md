DataGather Tool
Purpose

DataGather is a deterministic Python tool that connects to NetSuite (SuiteTalk REST) and executes a SuiteQL query. It is designed to be the “data extraction layer” for later automation (analysis, email logic, etc.).

At this stage, DataGather is a tool (not an agent): it does not make decisions; it only retrieves data.

What DataGather Does

Accepts a properly formatted SuiteQL string as input.

Loads NetSuite connection credentials from a .env file.

Authenticates to NetSuite using Token-Based Authentication (TBA) (OAuth1-style request signing).

Sends the SuiteQL query to NetSuite’s SuiteQL REST endpoint.

Receives a response from NetSuite in JSON format.

Returns the result rows (the JSON items array) to the caller (and currently prints sample fields for debugging).

Inputs
1) SuiteQL Query (string)

A SuiteQL query string such as:

PO header query (transactions table)

PO line query (transactionLine table joined to transaction)

Queries may include custom line fields (e.g. custcol1 for due date)

2) Environment Variables (.env)

Stored in the project root (not in src/):

Required:

NS_ACCOUNT_ID

NS_REST_BASE_URL

NS_CONSUMER_KEY

NS_CONSUMER_SECRET

NS_TOKEN_ID

NS_TOKEN_SECRET

Outputs
JSON response (NetSuite SuiteQL response)

NetSuite returns a JSON object containing:

items: list of rows (each row is a JSON object / Python dict)

hasMore, count, offset, totalResults: paging metadata (not implemented yet)

DataGather currently uses:

items as the main returned dataset (list of rows)

How It Works (High Level)
Authentication

Uses NetSuite TBA credentials:

Consumer Key/Secret (identifies the integration)

Token ID/Secret (identifies the user+role and permissions)

Requests are signed using OAuth1 signing via requests-oauthlib.

Header includes:

Accept: application/json

Content-Type: application/json

Prefer: transient (required in our environment)

Request

Endpoint:

{NS_REST_BASE_URL}/services/rest/query/v1/suiteql

HTTP method: POST

Body:

{ "q": "<SuiteQL query string>" }

Response

HTTP 200 indicates success

Data is returned as JSON

Each row is a dict (example keys depend on query aliases like po_number, line_no, etc.)

Current Example Queries
PO Header Example

Returns recent purchase order headers from the transaction table.

PO Line Example (with custom fields)

Joins transaction and transactionLine and returns:

PO id + PO number

Vendor name (display formatted)

Vendor email (via LEFT JOIN Vendor)

Line number, item

Promise date (custcol_atlas_wd_promise_date)

Due date (custcol1)

Qty ordered, qty received (quantityshiprecv)

Qty open (calculated)

Qty on shipments (quantityonshipments, defaulted with COALESCE)

Known Data Issues / Handling

Some lines may be missing due dates (custcol1 is NULL).

NetSuite may omit keys for NULL fields, so code uses .get() to avoid crashes.

Data cleanup is planned, and due date will be enforced as mandatory after cleanup.