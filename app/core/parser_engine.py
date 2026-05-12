import re
from io import BytesIO
from docx import Document

def extract_bank_specifications(docx_bytes: bytes) -> dict:
    """
    Parses the returned RGT Word document and extracts technical details.
    Includes smart-cleaning to remove placeholder instructions.
    """
    doc = Document(BytesIO(docx_bytes))
    extracted_data = {}
    
    if not doc.tables:
        raise ValueError("Returned document is missing the requirement table.")
        
    rgt_table = doc.tables[0]
    
    field_map = {
        "Base URL": ["url", "base_url", "baseUrl", "apiUrl", "api_url"],
        "API Type": ["apiType", "api_type"],
        "Authentication Method": ["apiAuth", "auth", "auth_method"],
        "Input Request Payload (JSON)": ["apiReq", "request_payload"],
        "Output Response Payload (JSON)": ["apiRes", "response_payload"]
    }

    for row in rgt_table.rows:
        if len(row.cells) < 2:
            continue
            
        label = row.cells[0].text.strip()
        raw_value = row.cells[1].text.strip()
        
        if label in field_map:
            # ---> BULLETPROOF CLEANUP <---
            # This uses Regex to find anything inside [brackets] and deletes it.
            # E.g., "https://api.com [Click to type]" becomes just "https://api.com"
            clean_value = re.sub(r'\[.*?\]', '', raw_value).strip()
            
            if clean_value: # If there is still text left after stripping brackets
                for db_key in field_map[label]:
                    extracted_data[db_key] = clean_value
                    
    # DEBUG PRINT
    print("\n" + "="*50)
    print("🧠 SMART PARSER EXTRACTED:")
    for key, val in extracted_data.items():
        # Truncate long JSON strings for cleaner terminal logs
        print(f"   - {key}: {val[:50]}..." if len(val) > 50 else f"   - {key}: {val}")
    print("="*50 + "\n")

    return extracted_data