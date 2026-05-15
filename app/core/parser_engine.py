import re
from io import BytesIO
from docx import Document


def extract_bank_specifications(docx_bytes: bytes) -> dict:
    """
    Parses the returned RGT Word document and extracts technical details.
    Maps the RGT table labels to the techDetails JSON keys used by details.js.
    """
    doc = Document(BytesIO(docx_bytes))
    extracted_data = {}

    if not doc.tables:
        raise ValueError("Returned document is missing the requirement table.")

    rgt_table = doc.tables[0]

    # Maps RGT label → techDetails JSON key(s)
    # Must match EXACTLY the labels in rgt_engine.py schema
    field_map = {
        "API Name":                     ["apiName"],
        "Business Purpose":             ["businessPurpose"],
        "API Type":                     ["apiType"],
        "Endpoint URL / Method Name":   ["endpointUrl"],
        "API Method":                   ["apiMethod"],
        "UAT URL":                      ["uatUrl"],
        "Prod URL":                     ["prodUrl"],
        "IP Whitelisting Required":     ["ipWhitelist"],
        "VPN / SSL Required":           ["vpnRequired"],
        "Authentication Type":          ["apiAuth"],
        "Token / Auth URL":             ["authDetails"],
        "Mandatory Headers":            ["mandatoryHeaders"],
        "Certificate / mTLS Notes":     ["certNotes"],
        "Sample Request Payload":       ["apiReq"],
        "Sample Response Payload":      ["apiRes"],
        "Error Response Sample":        ["errorSample"],
        "Timeout Value":                ["timeout"],
        "Rate Limit / TPS":             ["rateLimitTps"],
        "Retry Mechanism":              ["retryMechanism"],
        "Correlation / Reference ID":   ["correlationId"],
        "Callback / Webhook Required":  ["callbackRequired"],
        "Swagger / WSDL / Postman":     ["swaggerUrl"],
    }

    for row in rgt_table.rows:
        if len(row.cells) < 2:
            continue

        label = row.cells[0].text.strip()
        raw_value = row.cells[1].text.strip()

        if label in field_map:
            # Remove placeholder text inside [brackets]
            clean_value = re.sub(r'\[.*?\]', '', raw_value).strip()

            if clean_value:
                for db_key in field_map[label]:
                    extracted_data[db_key] = clean_value

    # Debug log
    print("\n" + "=" * 50)
    print("PARSER EXTRACTED:")
    for key, val in extracted_data.items():
        display = f"{val[:60]}..." if len(val) > 60 else val
        print(f"   - {key}: {display}")
    print("=" * 50 + "\n")

    return extracted_data