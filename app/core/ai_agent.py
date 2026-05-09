import os
import boto3
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

# Load the variables from the .env file
load_dotenv()

# Securely grab AWS configuration
AWS_REGION = os.getenv("AWS_BEDROCK_REGION", "us-east-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

# SAFELY initialize the AWS Bedrock client
try:
    # Boto3 automatically reads AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY from your .env
    bedrock_client = boto3.client(
        service_name='bedrock-runtime',
        region_name=AWS_REGION
    )
except Exception as e:
    bedrock_client = None
    print(f"⚠️ WARNING: AWS Bedrock initialization failed. AI Agents are offline. Error: {e}")

def _invoke_bedrock(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """Helper function to securely call AWS Bedrock's Converse API."""
    if not bedrock_client:
        raise Exception("Bedrock client is offline.")
        
    try:
        response = bedrock_client.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            system=[{"text": system_prompt}],
            inferenceConfig={"temperature": temperature}
        )
        return response['output']['message']['content'][0]['text'].strip()
    except ClientError as e:
        print(f"AWS Bedrock API Error: {e}")
        raise e

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
        return _invoke_bedrock(system_prompt, user_prompt, temperature=0.3)
    except Exception as e:
        print(f"AI Agent Summarization Failed via Bedrock: {e}")
        return "Please review the detailed logs below for the latest status."


def generate_stakeholder_intro(team_name: str, team_items: list) -> str:
    """Generates a stakeholder-ready introductory paragraph for the email."""
    if not bedrock_client:
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
        return _invoke_bedrock(system_prompt, user_prompt, temperature=0.4)
    except Exception as e:
        print(f"Executive Summary Generation Failed via Bedrock: {e}")
        return f"<p>Please review the {len(team_items)} pending items below requiring your sign-off to unblock the current project phase.</p>"


def generate_project_mom(project_data: str) -> str:
    """Synthesizes raw database logs into a formal Minutes of Meeting (MOM)."""
    if not bedrock_client:
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
        return _invoke_bedrock(system_prompt, user_prompt, temperature=0.3)
    except Exception as e:
        print(f"MOM Generation Failed via Bedrock: {e}")
        return "<p>Error generating MOM. Please review the dashboard manually.</p>"
def generate_wud_summary(purpose: str, raw_notes: str) -> str:
    """Generates an Executive Architecture Summary using the existing AWS Bedrock config."""
    
    if not raw_notes or str(raw_notes).strip() == "":
        return "No specific architectural decisions or workshop notes were recorded."

    if not bedrock_client:
        return "AI Agent offline. Please review raw workshop notes manually."

    system_prompt = """
    You are an Enterprise Integration Architect.
    Write a 1 to 2 paragraph "Executive Architecture Summary" that explains what this API does, the architectural decisions made, and any major action items. 
    
    Rules:
    1. DO NOT use HTML. Output plain text only. 
    2. Be highly professional, objective, and concise.
    3. Base your summary STRICTLY on the provided business purpose and raw workshop notes.
    """

    user_prompt = f"Business Purpose: {purpose}\n\nRaw Notes:\n{raw_notes}"

    try:
        # Utilizing your existing helper function with a low temperature for professional formatting
        return _invoke_bedrock(system_prompt, user_prompt, temperature=0.2)
    except Exception as e:
        print(f"WUD Summary Generation Failed via Bedrock: {e}")
        return "Error:  Not Able to generate AI summary due to an API issue. Please review raw workshop notes manually."