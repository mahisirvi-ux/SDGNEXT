import os
from dotenv import load_dotenv
import openai

# Load the variables from the .env file into Python's memory
load_dotenv()

# Securely grab the keys
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("AI_MODEL_NAME", "gpt-4o-mini") # Falls back to 4o-mini if not found

# Initialize the client
client = openai.OpenAI(api_key=API_KEY)

def generate_blocker_summary(touchpoint_name: str, team_name: str, history_logs: list) -> str:
    """
    AI Agent: Analyzes raw timeline logs and generates a 1-2 sentence executive summary.
    """
    if not history_logs:
        return "No historical context available. Please review initial requirements."

    timeline_text = ""
    for log in history_logs:
        date_str = log.created_at.strftime("%b %d") if log.created_at else "Unknown"
        pointer = log.open_pointer_history or ""
        comment = log.comment or ""
        timeline_text += f"- [{date_str}] Action/Pointer: {pointer} | Comment: {comment}\n"

    system_prompt = f"""
    You are an expert IT Project Manager Agent for the SDGNext Command Center.
    Your job is to read a raw timeline of database updates and summarize the status and highlight the next action along with risk information to delay in project delivery.
    
    Rules:
    1. Output strictly 1 to 2 sentences.
    2. Be direct and professional.
    3. Identify exactly what the {team_name} needs to do next to unblock the '{touchpoint_name}' integration.
    4. Do not use greetings or fluff. Just state the status and the required action.
    5. If the logs indicate a resolved issue, summarize the resolution and current status instead.
    6. Always assume the reader is an executive who needs a quick, clear update without technical jargon.
    7. If the logs are insufficient to determine the blocker, state that clearly and suggest reviewing the logs for more details.
    8. Do not make assumptions beyond the provided logs. If the logs are ambiguous, state that ambiguity in your summary.
    9. Always end with a clear next step for the team, even if it's just "Please review the timeline logs for more details."
    10.highlight riskiest pointer in the logs and make it bold in the summary.
    
     Here are the Timeline Logs for '{touchpoint_name}':
     Team: {team_name}
     --------------------------------
     {timeline_text}
     --------------------------------
     Based on the above
    
    Timeline Logs:
    {timeline_text}
    """

    try:
        # --- LIVE API CALL ---
        response = client.chat.completions.create(
            model=MODEL_NAME, 
            temperature=0.3, # Low temperature keeps it analytical and factual
            messages=[
                {"role": "system", "content": "You are a concise Project Management AI."},
                {"role": "user", "content": system_prompt}
            ]
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"AI Agent Summarization Failed: {e}")
        return "Please review the detailed logs below for the latest status."
def generate_stakeholder_intro(team_name: str, team_items: list) -> str:
    """
    Reads all pending items for a specific team and generates a highly professional, 
    stakeholder-ready introductory paragraph for the email.
    """
    if not client:
        return f"Please review the {len(team_items)} pending items below requiring your sign-off to unblock the current project phase."

    # 1. Format the data so the LLM understands the full context
    context_text = f"Team: {team_name}\nTotal Pending Items: {len(team_items)}\n\nDetails:\n"
    for item in team_items:
        context_text += f"- Touchpoint: {item['touchpoint']} (Module: {item['module']})\n"
        context_text += f"  Status/Blocker: {item['ai_summary']}\n\n"

    # 2. The Stakeholder Prompt
    system_prompt = f"""
    You are an Executive Delivery Manager for an enterprise banking transformation project.
    Your goal is to write a short, highly professional email introduction to the '{team_name}'.
    
    Data Provided:
    {context_text}
    
    Rules for your response:
    1. Write exactly 1 or 2 paragraphs. No more.
    2. Tone must be polite, urgent, and professional (C-Suite level).
    3. Synthesize the overall status. (e.g., "We are currently tracking 2 critical items holding up the Onboarding module...")
    4. Do not list the items out with bullet points (the email template will do that later). Just provide the narrative summary.
    5. Do not include greetings ("Dear Team") or sign-offs ("Thanks, PM"). Just output the body paragraphs.
    6. Format your response with basic HTML paragraph tags (<p>text</p>) so it renders perfectly in the email.
    """

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME, 
            temperature=0.4, # Slightly higher temperature for better narrative flow
            messages=[
                {"role": "system", "content": "You are a professional Executive IT Communicator."},
                {"role": "user", "content": system_prompt}
            ]
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"Executive Summary Generation Failed: {e}")
        return f"<p>Please review the {len(team_items)} pending items below requiring your sign-off to unblock the current project phase.</p>"

def generate_project_mom(project_data: str) -> str:
    """
    AI Agent: Synthesizes raw database logs into a formal Minutes of Meeting (MOM) document.
    """
    if not client:
        return "<p>AI Agent offline. Cannot generate MOM.</p>"

    system_prompt = f"""
    You are an expert IT Project Management Officer (PMO) for an enterprise integration project.
    I will provide you with a raw dump of all database updates, discussions, and open pointers recorded recently.

    Your job is to synthesize this raw data into a highly professional, structured 'Minutes of Meeting' (MOM) / Status Report.

    Raw Project Data:
    {project_data}

    Format your output strictly using HTML tags for an email body. 
    You MUST include the following 3 sections:
    1. <h3>Executive Summary</h3> (A 2-3 sentence high-level overview of project health based on the data).
    2. <h3>Key Discussions & Decisions</h3> (Group the technical context/remarks by Module or Team. Use bullet points).
    3. <h3>Pending Action Items</h3> (A clear, urgent list of exactly who needs to do what to unblock the project).

    Rules:
    - Tone: Formal, objective, and C-Suite ready.
    - Do NOT invent data. If no data exists for a section, state "No significant updates."
    - Output ONLY the HTML content. Do not include ```html blocks or outer <html>/<body> tags.
    """

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME, 
            temperature=0.3, # Keep it highly factual
            messages=[
                {"role": "system", "content": "You are an elite Project Manager AI."},
                {"role": "user", "content": system_prompt}
            ]
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"MOM Generation Failed: {e}")
        return "<p>Error generating MOM. Please review the dashboard manually.</p>"