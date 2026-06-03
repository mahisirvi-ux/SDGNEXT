import os
import json
import re
import boto3
import xml.etree.ElementTree as ET
from openai import OpenAI
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Load the variables from the .env file
load_dotenv()

# =========================================================================
# MULTI-PROVIDER AI ENGINE (OpenAI + AWS Bedrock)
# Switch at runtime via: POST /api/admin/ai-provider
# =========================================================================

# --- Provider Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID", "gpt-4o-mini")

AWS_BEDROCK_REGION = os.getenv("AWS_BEDROCK_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")

# --- Active Provider State (mutable at runtime) ---
# Options: "openai" | "bedrock"
_active_provider = os.getenv("AI_PROVIDER", "bedrock").lower()


def get_active_provider() -> str:
    """Returns the currently active AI provider name."""
    return _active_provider


def set_active_provider(provider: str) -> str:
    """Switch the active AI provider at runtime. Returns the new active provider."""
    global _active_provider
    provider = provider.strip().lower()
    if provider not in ("openai", "bedrock"):
        raise ValueError(f"Invalid provider '{provider}'. Must be 'openai' or 'bedrock'.")
    _active_provider = provider
    print(f"[AI] Provider switched to: {_active_provider.upper()}")
    return _active_provider


# --- Initialize OpenAI Client ---
openai_client = None
try:
    if OPENAI_API_KEY:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        print("[AI] OpenAI client initialized.")
    else:
        print("[AI] WARNING: OPENAI_API_KEY not found. OpenAI provider unavailable.")
except Exception as e:
    print(f"[AI] WARNING: OpenAI initialization failed: {e}")

# --- Initialize AWS Bedrock Client ---
bedrock_client = None
try:
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_BEDROCK_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                )
        print(f"[AI] AWS Bedrock client initialized (region: {AWS_BEDROCK_REGION}, model: {BEDROCK_MODEL_ID}).")
    else:
        print("[AI] WARNING: AWS credentials not found. Bedrock provider unavailable.")
except Exception as e:
    print(f"[AI] WARNING: AWS Bedrock initialization failed: {e}")

# --- Unified client reference (for backward-compat "if not client" checks) ---
# This is True if ANY provider is available
client = openai_client or bedrock_client


# =========================================================================
# PROVIDER INVOCATION FUNCTIONS
# =========================================================================

def _invoke_openai(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """Call OpenAI's Chat Completion API."""
    if not openai_client:
        raise Exception("OpenAI client is not initialized. Check OPENAI_API_KEY.")

    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL_ID,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=temperature
    )
    return response.choices[0].message.content.strip()


def _invoke_bedrock(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """Call AWS Bedrock (Anthropic Claude) via the Converse API."""
    if not bedrock_client:
        raise Exception("Bedrock client is not initialized. Check AWS credentials.")

    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [{"text": user_prompt}]
            }
        ],
        system=[{"text": system_prompt}],
        inferenceConfig={
            "temperature": temperature,
            "maxTokens": 4096,
        },
    )
    # Extract text from Converse API response
    output_message = response["output"]["message"]
    result_text = ""
    for block in output_message["content"]:
        if "text" in block:
            result_text += block["text"]
    return result_text.strip()


def _invoke_llm(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """Unified LLM invocation - routes to the active provider with automatic fallback."""
    primary = _active_provider
    fallback = "openai" if primary == "bedrock" else "bedrock"

    # Try primary provider
    try:
        if primary == "openai":
            return _invoke_openai(system_prompt, user_prompt, temperature)
        else:
                        return _invoke_bedrock(system_prompt, user_prompt, temperature)
    except Exception as primary_err:
        print(f"[AI] Primary provider [{primary.upper()}] failed: {primary_err}")
        print(f"[AI] Attempting fallback to [{fallback.upper()}]...")

    # Try fallback provider
    try:
        if fallback == "openai":
            return _invoke_openai(system_prompt, user_prompt, temperature)
        else:
            return _invoke_bedrock(system_prompt, user_prompt, temperature)
    except Exception as fallback_err:
        print(f"[AI] Fallback provider [{fallback.upper()}] also failed: {fallback_err}")
        raise Exception(
            f"All AI providers failed. Primary [{primary}]: {primary_err} | "
            f"Fallback [{fallback}]: {fallback_err}"
        )

# -------------------------------------------------------------------------
# AI AGENT FUNCTIONS
# -------------------------------------------------------------------------

def generate_blocker_summary(touchpoint_name: str, team_name: str, history_logs: list) -> str:
    """Generates a 1-2 sentence executive summary of the current blocker."""
    if not history_logs:
        return "No historical context available. Please review initial requirements."

    if not client:
        return "Please review the detailed logs below for the latest status. (AI Agent offline)"

    timeline_text = ""
    for log in history_logs:
        date_str = log.created_at.strftime("%b %d") if log.created_at else "Unknown"
        pointer = log.open_pointer_history or ""
        comment = log.comment or ""
        timeline_text += f"- [{date_str}] Action/Pointer: {pointer} | Comment: {comment}\n"

    system_prompt = f"""
    You are an expert IT Project Manager Agent for the SDGNext Command Center.
    Your job is to read a raw timeline of database updates and summarize the current blocker for the {team_name}.
    Rules:
    1. Output strictly 1 to 2 sentences.
    2. Be direct and professional.
    3. Identify exactly what the {team_name} needs to do next to unblock the '{touchpoint_name}' integration.
    4. Do not use greetings or fluff. Just state the status and the required action.
        """
    
    user_prompt = f"Timeline Logs:\n{timeline_text}"

    try:
        return _invoke_llm(system_prompt, user_prompt, temperature=0.3)
    except Exception as e:
        print(f"AI Agent Summarization Failed: {e}")
        return "Please review the detailed logs below for the latest status."


def generate_stakeholder_intro(team_name: str, team_items: list) -> str:
    """Generates a stakeholder-ready introductory paragraph for the email."""
    if not client:
        return f"<p>Please review the {len(team_items)} pending items below requiring your sign-off to unblock the current project phase.</p>"

    context_text = f"Team: {team_name}\nTotal Pending Items: {len(team_items)}\n\nDetails:\n"
    for item in team_items:
        context_text += f"- Touchpoint: {item['touchpoint']} (Module: {item['module']})\n"
        context_text += f"  Status/Blocker: {item['ai_summary']}\n\n"

    system_prompt = f"""
    You are an Executive Delivery Manager for an enterprise banking transformation project.
    Your goal is to write a short, highly professional email introduction to the '{team_name}'.
    Rules:
    1. Write exactly 1 or 2 paragraphs. No more.
    2. Tone must be polite, urgent, and professional (C-Suite level).
    3. Synthesize the overall status.
    4. Do not list the items out with bullet points. Just provide the narrative summary.
    5. Do not include greetings or sign-offs.
    6. Format your response with basic HTML paragraph tags (<p>text</p>).
        """

    user_prompt = f"Data Provided:\n{context_text}"

    try:
        return _invoke_llm(system_prompt, user_prompt, temperature=0.4)
    except Exception as e:
        print(f"Executive Summary Generation Failed: {e}")
        return f"<p>Please review the {len(team_items)} pending items below requiring your sign-off to unblock the current project phase.</p>"


def generate_project_mom(project_data: str) -> str:
    """Synthesizes raw database logs into a formal Minutes of Meeting (MOM)."""
    if not client:
        return "<p>AI Agent offline. Cannot generate MOM.</p>"

    system_prompt = """
    You are an expert IT Project Management Officer (PMO) for an enterprise integration project.
    Synthesize the raw project data into a highly professional, structured 'Minutes of Meeting' (MOM).

    Format your output strictly using HTML tags for an email body. Include:
    1. <h3>Executive Summary</h3> (A 2-3 sentence high-level overview of project health).
    2. <h3>Key Discussions & Decisions</h3> (Group by Module or Team. Use bullet points).
    3. <h3>Pending Action Items</h3> (A clear list of who needs to do what to unblock the project).

    Rules:
    - Tone: Formal, objective, and C-Suite ready.
    - Do NOT invent data. If no data exists, state "No significant updates."
    - Output ONLY the HTML content. Do not include markdown code blocks (```html) or outer <html>/<body> tags.
        """

    user_prompt = f"Raw Project Data:\n{project_data}"

    try:
        return _invoke_llm(system_prompt, user_prompt, temperature=0.3)
    except Exception as e:
        print(f"MOM Generation Failed: {e}")
        return "<p>Error generating MOM. Please review the dashboard manually.</p>"


def generate_wud_content(api_name: str, module_name: str, crm_location: str, business_flow: str, input_req: str, output_res: str, integration_type: str = "api") -> dict:
    """Generates formal Introduction, Macro Logic, and Expected Output for the WUD."""
    
    # Fallback if OpenAI is offline
    if not client:
        return {
            "introduction": f"The '{api_name}' API under the {module_name} module is triggered from {crm_location} to facilitate data transfer.",
            "macro_logic": "• AI Agent offline.\n• Please review manually.",
            "expected_output": "• AI Agent offline.\n• Please review manually."
        }

    system_prompt = """
    You are an expert Enterprise Integration Business Analyst. 
    Translate the provided inputs into formal technical specifications for a Work Unit Document (WUD).

    You must output your response STRICTLY as a JSON object with exactly three keys: "introduction", "macro_logic", and "expected_output".

    Key 1: "introduction"
    - Write a professional, concise 2 to 3 line overview.
    - You MUST explicitly name the Module.
    - You MUST explicitly state where the API is called within the CRM (e.g., Lead Journey, Onboarding Process, Specific Layout).
    - Explain the core business purpose of the API.
    - Output as a standard text paragraph (no bullet points).

    Key 2: "macro_logic"
    - Write a step-by-step flow based on the provided Business Flow.
    - Explicitly state: "Input Parameters will be:" followed by a summary of the provided Input Details.
    - Explicitly state: "Based On Input Parameter, Output Parameter will be:" followed by a summary of the Output Details.
    - Output as a bulleted list (use the '•' character and newlines '\n').

    Key 3: "expected_output"
    - Output as a bulleted list (use the '•' character and newlines '\n').
    - Bullet 1 MUST start with: "In the success scenario, when valid input is passed, the system will..." and describe the successful outcome based on the Output Details.
    - Bullet 2 MUST be exactly: "In Failure Scenario, If Invalid Response is passed it will display respective error messages in response."

    Do not include markdown code blocks (like ```json). Return ONLY the raw, valid JSON object.
        """

    user_prompt = f"API Name: {api_name}\nModule: {module_name}\nTrigger Location in CRM: {crm_location}\nBusiness Flow / Objective: {business_flow}\n\nInput Details:\n{input_req}\n\nOutput Details:\n{output_res}"

    try:
        response_text = _invoke_llm(system_prompt, user_prompt, temperature=0.2)

        # Strip accidental markdown formatting the LLM might have added
        clean_json = re.sub(r'```json|```', '', response_text).strip()
        return json.loads(clean_json)

    except Exception as e:
        print(f"WUD Content Generation Failed: {e}")
        return {
            "introduction": f"The '{api_name}' integration facilitates seamless data transfer.",
            "macro_logic": "• Error: Could not generate logic.\n• Please check API.",
            "expected_output": "• Error: Could not generate output.\n• Please check API."
        }


def generate_touchpoint_mom(
    touchpoint_name: str,
    module: str,
    action_items: list,
    discussions: list,
    open_pointers: str = None,
) -> str:
    """Returns HTML body for a touchpoint-level MoM email."""

    # Build fallback HTML (used when OpenAI is offline or fails)
    fallback_rows = ""
    for item in action_items:
        fallback_rows += (
            f"<tr><td style='border:1px solid #e2e8f0;padding:8px;'>{item.get('description','')}</td>"
            f"<td style='border:1px solid #e2e8f0;padding:8px;'>{item.get('action_point','')}</td>"
            f"<td style='border:1px solid #e2e8f0;padding:8px;'>{item.get('owner','')}</td>"
            f"<td style='border:1px solid #e2e8f0;padding:8px;'>{item.get('expected_date','')}</td></tr>"
        )

    disc_html = ""
    for d in discussions:
        disc_html += f"<li>{d.get('content','')} <em>({d.get('created_at','')})</em></li>"

    fallback_html = (
        f"<h3>Meeting Context</h3>"
        f"<p><strong>Touchpoint:</strong> {touchpoint_name}<br><strong>Module:</strong> {module}</p>"
        f"<h3>Discussion Summary</h3>"
        f"<ul>{disc_html if disc_html else '<li>No discussions recorded.</li>'}</ul>"
        f"<h3>Action Items</h3>"
        f"<table style='border-collapse:collapse;width:100%;font-size:13px;'>"
        f"<thead><tr style='background:#f1f5f9;'>"
        f"<th style='border:1px solid #e2e8f0;padding:8px;text-align:left;'>Description</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px;text-align:left;'>Action Point</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px;text-align:left;'>Owner</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px;text-align:left;'>Expected Date</th>"
        f"</tr></thead><tbody>"
        f"{fallback_rows if fallback_rows else '<tr><td colspan=4 style=border:1px solid #e2e8f0;padding:8px;>No action items.</td></tr>'}"
        f"</tbody></table>"
    )

    if open_pointers:
        fallback_html += f"<h3>Open Pointers</h3><p>{open_pointers}</p>"

    if not client:
        return fallback_html

    # Build AI prompt
    actions_text = ""
    for i, item in enumerate(action_items, 1):
        actions_text += (
            f"{i}. Description: {item.get('description','')} | "
            f"Action: {item.get('action_point','')} | "
            f"Owner: {item.get('owner','')} | "
            f"Due: {item.get('expected_date','')}\n"
        )

    discussions_text = ""
    for d in discussions:
        discussions_text += f"- [{d.get('created_at','')}] {d.get('content','')}\n"

    system_prompt = (
        "You are an expert IT Project Management Officer (PMO) for an enterprise CRM integration project. "
        "Generate a formal, professional Minutes of Meeting (MoM) for a single integration touchpoint. "
        "Format your output strictly using HTML tags. Include these sections: "
        "1. <h3>Meeting Context</h3> - Touchpoint name, module, and brief context. "
        "2. <h3>Discussion Summary</h3> - Synthesize the discussions into 2-4 concise bullet points. "
        "3. <h3>Action Items</h3> - An HTML table with columns: Description, Action Point, Owner, Expected Date. "
        "4. <h3>Open Pointers</h3> - Only include if open pointers are provided. "
        "Rules: Tone is formal, objective, C-Suite ready. Do NOT invent data. Only use what is provided. "
        "Output ONLY the HTML content. No markdown fences, no outer html/body tags. Keep it concise but complete."
    )

    user_prompt = (
        f"Touchpoint: {touchpoint_name}\n"
        f"Module: {module}\n\n"
        f"Discussions:\n{discussions_text if discussions_text else 'None recorded.'}\n\n"
                f"Action Items:\n{actions_text if actions_text else 'None recorded.'}\n\n"
                f"Open Pointers: {open_pointers or 'None.'}"
    )

    try:
        return _invoke_llm(system_prompt, user_prompt, temperature=0.3)
    except Exception as e:
        print(f"Touchpoint MoM Generation Failed: {e}")
        return fallback_html

def generate_eds_request_template(payload: str) -> str:
    """Generates a dynamic request template by replacing literal values with ##KEY##."""
    if not client:
        return "{\n  \"ERROR\": \"AI Agent offline\"\n}"

    system_prompt = """
    You are an expert enterprise integration developer. Your task is to convert the provided JSON or XML payload into a dynamic request template.
    Rule 1: Keep the exact structural integrity of the original payload.
    Rule 2: Replace all literal values with dynamic placeholders in the format ##KEY_NAME_UPPERCASE##.
    Rule 3: Return ONLY the raw template string. Do not include markdown code blocks (like ```json).
        """
    
    try:
        return _invoke_llm(system_prompt, f"Payload:\n{payload}", temperature=0.1).strip()
    except Exception as e:
        print(f"EDS Template Gen Failed: {e}")
        return f"Error generating template: {e}"

def _extract_output_params_from_xslt(xslt_str: str) -> list:
    """Deterministically extract output parameter names from generated XSLT.

    Finds all XML element tags that contain an <xsl:value-of select="..."/>
    child. These are the actual output field names for MASHUPDATASOURCEFIELD.

    Excludes structural/wrapper tags like 'response', 'xsl:template',
    'xsl:stylesheet', etc.

    Example XSLT fragment:
        <Status><xsl:value-of select="status"/></Status>
    Extracts: "Status"
    """
    # Pattern: <TagName> followed (possibly with whitespace) by <xsl:value-of
    # This catches both single-line and multi-line variants
    pattern = r'<([A-Za-z][A-Za-z0-9_]*)>\s*<xsl:value-of\s+select='
    matches = re.findall(pattern, xslt_str)

    # Exclude structural/wrapper tags
    excluded = {
        'response', 'root', 'template', 'stylesheet',
        'xsl:template', 'xsl:stylesheet', 'xsl:output',
        'output', 'transform'
    }

    seen = set()
    params = []
    for tag in matches:
        tag_lower = tag.lower()
        if tag_lower not in excluded and tag not in seen:
            seen.add(tag)
            params.append(tag)

    return params


def generate_eds_xslt_config(success_payload: str, error_payload: str) -> dict:
    """Generates XSLT for the success and error responses and extracts output parameters.

    Strategy:
    1. AI generates a clean XSLT 1.0 stylesheet handling both success and failure using <xsl:choose>.
    2. Dynamic Root Matching: It detects if the input is JSON (uses match="/root") or XML (uses match="/*").
    3. It balances the XML tags: ALL unique fields from BOTH payloads will be represented.
    4. Output parameters are extracted DETERMINISTICALLY by parsing the generated XSLT.

    Returns:
        {"xslt": str, "parameters": [str, ...]}
    """
    if not client: 
        return {"xslt": "", "parameters": []}

    system_prompt = """You are an expert XSLT 1.0 developer for a CRM integration platform.

Your task: Generate a clean XSLT 1.0 stylesheet that transforms the provided API responses (which could be JSON or XML) into a flat XML structure, handling BOTH success and failure scenarios.

Rules:
1. Detect Input Format:
   - If the payloads are JSON: The CRM engine wraps JSON responses in a <root> element, so you MUST use <xsl:template match="/root">.
   - If the payloads are XML: Do NOT use match="/root". Instead, use <xsl:template match="/*"> to dynamically match the provided top-level XML element (e.g., <ApiResponse>).
2. Create a single <response> wrapper element inside the template.
3. Identify a distinguishing field to check for success vs failure (e.g., status='SUCCESS' or Header/Status='SUCCESS') and use <xsl:choose>, <xsl:when test="...">, and <xsl:otherwise> to branch the logic. Evaluate the condition relative to the matched root element.
4. CRITICAL "BALANCED TAGS" RULE: You must identify the UNION of all unique fields/elements from BOTH the Success and Error payloads. Convert these field names to PascalCase XML tags.
5. In the <xsl:when> (Success) block:
   - Map the success fields using <xsl:value-of select="relative/path/to/originalField"/>.
   - For fields that ONLY exist in the error payload, output empty tags (e.g., <ErrorSpecificField></ErrorSpecificField>).
6. In the <xsl:otherwise> (Error) block:
   - Map the error fields using <xsl:value-of select="relative/path/to/originalField"/>.
   - For fields that ONLY exist in the success payload, output empty tags (e.g., <SuccessSpecificField></SuccessSpecificField>).
7. The order of tags inside the <xsl:when> and <xsl:otherwise> blocks MUST be exactly the same to ensure a consistent XML structure.
8. Use standard XSLT 1.0 boilerplate: xml declaration, xsl:stylesheet with version="1.0" and xmlns:xsl, xsl:output method="xml" indent="yes".
9. Return ONLY the raw XSLT code. Do not wrap in markdown code blocks. Do not add any explanation text.
"""

    user_prompt = f"Success Response Payload:\n{success_payload}\n\nError Response Payload:\n{error_payload}"

    try:
        xslt_str = _invoke_llm(system_prompt, user_prompt, temperature=0.1).strip()

        # Strip any accidental markdown fences generated by the LLM
        # (Constructed dynamically to prevent UI markdown parser from breaking)
        fence = '`' * 3
        xslt_str = re.sub(r'^' + fence + r'(?:xml|xslt)?\s*', '', xslt_str)
        xslt_str = re.sub(r'\s*' + fence + r'$', '', xslt_str)
        xslt_str = xslt_str.strip()

        parameters = []
        
        # Deterministically extract output parameters from the XSLT using regex
        try:
            # Finds PascalCase tags containing xsl:value-of 
            matches = re.findall(r'<([A-Z][a-zA-Z0-9_]*?)>\s*<xsl:value-of', xslt_str)
            if matches:
                # Use dict.fromkeys to remove duplicates while preserving exact order
                parameters = list(dict.fromkeys(matches))
        except Exception:
            pass

        # Fallback: parse field names directly from BOTH payloads (Supports JSON & XML)
        if not parameters and (success_payload or error_payload):
            try:
                payload_keys = set()
                for payload in [success_payload, error_payload]:
                    if not payload:
                        continue
                    payload = payload.strip()
                    
                    if payload.startswith('{') or payload.startswith('['):
                        # JSON Fallback
                        obj = json.loads(payload)
                        if isinstance(obj, dict):
                            payload_keys.update(obj.keys())
                    elif payload.startswith('<'):
                        # XML Fallback
                        try:
                            root = ET.fromstring(payload)
                            for elem in root.iter():
                                if len(elem) == 0:  # If it's a leaf node
                                    # Strip XML namespace if present
                                    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                                    payload_keys.add(tag)
                        except ET.ParseError:
                            pass
                
                for key in payload_keys:
                    # Convert to PascalCase
                    pascal = key[0].upper() + key[1:] if key else key
                    if pascal not in parameters:
                        parameters.append(pascal)
            except Exception:
                pass

        return {"xslt": xslt_str, "parameters": parameters}

    except Exception as e:
        print(f"EDS XSLT Gen Failed: {e}")
        return {"xslt": "", "parameters": []}



def generate_crm_headers_xml(
    mandatory_headers_str: str,
    service_location: str,
    api_name: str
) -> dict:
    """Generate CRM XML headers from the mandatory headers string.

    DETERMINISTIC - no AI. Parses the comma-separated header string
    directly into <Header Name="..." Value="..." /> elements.

    Supported input formats:
        "Content-Type: application/json, Authorization:Bearer xyz"
        "Content-Type, Authorization, X-Request-ID"

    If a header has a colon, everything after the first colon is the value.
    If a header has no colon, the header name is used as the value placeholder.

    Args:
        mandatory_headers_str: comma-separated headers (with optional values)
        service_location: the UAT URL (unused, kept for API compat)
        api_name: the API name (unused, kept for API compat)

    Returns:
        {
            "header_variables_xml": str,
            "header_variables_xml_escaped": str,
            "error": str or None
        }
    """
    FALLBACK_XML = '<Headers>\n<Header Name="Content-Type" Value="application/json" />\n</Headers>'

    def _escape_xml(raw: str) -> str:
        return (raw
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    if not mandatory_headers_str or not mandatory_headers_str.strip():
        return {
            "header_variables_xml": FALLBACK_XML,
            "header_variables_xml_escaped": _escape_xml(FALLBACK_XML),
            "error": "No mandatory headers provided - using default."
        }

    # Parse comma-separated headers
    raw_parts = [h.strip() for h in mandatory_headers_str.split(",") if h.strip()]

    header_lines = []
    for part in raw_parts:
        if ":" in part:
            # Split on first colon: "Content-Type: application/json" -> ("Content-Type", "application/json")
            name, value = part.split(":", 1)
            name = name.strip()
            value = value.strip()
        else:
            # No colon - header name only, use name as placeholder value
            name = part.strip()
            value = name

        if name:
            # Escape XML special chars in values
            safe_value = (value
                          .replace('&', '&amp;')
                          .replace('<', '&lt;')
                          .replace('>', '&gt;')
                          .replace('"', '&quot;'))
            safe_name = (name
                         .replace('&', '&amp;')
                         .replace('<', '&lt;')
                         .replace('>', '&gt;')
                         .replace('"', '&quot;'))
            header_lines.append(f'<Header Name="{safe_name}" Value="{safe_value}" />')

    if not header_lines:
        return {
            "header_variables_xml": FALLBACK_XML,
            "header_variables_xml_escaped": _escape_xml(FALLBACK_XML),
            "error": "Could not parse any headers - using default."
        }

    xml = "<Headers>\n" + "\n".join(header_lines) + "\n</Headers>"

    return {
        "header_variables_xml": xml,
        "header_variables_xml_escaped": _escape_xml(xml),
        "error": None
    }
