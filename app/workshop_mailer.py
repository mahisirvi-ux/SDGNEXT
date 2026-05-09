import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, timedelta, datetime
from collections import defaultdict
from app.core.database import SessionLocal
from app.models.domain import IntegrationTouchpoint, IDRFunctional, IDRTechnical, TeamMaster

# --- CONFIGURATION (Re-using your Phase 1 Setup) ---
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
SMTP_USERNAME = "mahi.sirvi@gmail.com"
SMTP_PASSWORD = "klrynpcgevlubkfj" 

# --- PRE-REQUISITE TEMPLATES (HTML Formatted) ---
# --- PRE-REQUISITE TEMPLATES (HTML Formatted) ---
PRE_REQS = {
    "api": """
    <div style="font-size: 12px; color: #475569; margin-top: 10px; line-height: 1.5;">
        <p style="margin-bottom: 15px; color: #dc2626; font-weight: bold;">
            ⚠️ Please prepare the following API Integration details prior to the discussion:
        </p>

        <div style="background-color: #f1f5f9; padding: 4px 8px; font-weight: bold; color: #0f172a; border-left: 3px solid #3b82f6;">1. Project Details</div>
        <table width="100%" cellpadding="6" style="border-collapse: collapse; margin: 5px 0 15px 0; border: 1px solid #e2e8f0; text-align: left;">
            <tr style="background-color: #f8fafc;"><th style="border: 1px solid #e2e8f0; width: 40%;">Item</th><th style="border: 1px solid #e2e8f0;">Details</th></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Project Name</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Consumer Application</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Provider Application</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Business Purpose</td><td style="border: 1px solid #e2e8f0;"></td></tr>
        </table>

        <div style="background-color: #f1f5f9; padding: 4px 8px; font-weight: bold; color: #0f172a; border-left: 3px solid #3b82f6;">2. API Details</div>
        <table width="100%" cellpadding="6" style="border-collapse: collapse; margin: 5px 0 15px 0; border: 1px solid #e2e8f0; text-align: left;">
            <tr style="background-color: #f8fafc;"><th style="border: 1px solid #e2e8f0; width: 40%;">Item</th><th style="border: 1px solid #e2e8f0;">Details</th></tr>
            <tr><td style="border: 1px solid #e2e8f0;">API Type</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">REST / SOAP</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Base URL</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Endpoint URL</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">HTTP Method</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">GET / POST / PUT</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Request Format</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">JSON / XML</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Response Format</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">JSON / XML</td></tr>
        </table>

        <div style="background-color: #f1f5f9; padding: 4px 8px; font-weight: bold; color: #0f172a; border-left: 3px solid #3b82f6;">3. Authentication & Security</div>
        <table width="100%" cellpadding="6" style="border-collapse: collapse; margin: 5px 0 15px 0; border: 1px solid #e2e8f0; text-align: left;">
            <tr style="background-color: #f8fafc;"><th style="border: 1px solid #e2e8f0; width: 40%;">Item</th><th style="border: 1px solid #e2e8f0;">Details</th></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Authentication Type</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">OAuth / JWT / API Key / Basic Auth</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Token URL</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">IP Whitelisting Required</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">Yes / No</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">SSL/VPN Required</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">Yes / No</td></tr>
        </table>

        <div style="background-color: #f1f5f9; padding: 4px 8px; font-weight: bold; color: #0f172a; border-left: 3px solid #3b82f6;">4. Request & Response Samples</div>
        <div style="margin: 5px 0 15px 0;">
            <strong>Sample Request</strong>
            <pre style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 8px; border-radius: 4px; font-family: monospace; color: #059669;">{\n  "customerId": "",\n  "referenceId": ""\n}</pre>
            
            <strong>Sample Success Response</strong>
            <pre style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 8px; border-radius: 4px; font-family: monospace; color: #2563eb;">{\n  "status": "SUCCESS",\n  "message": "Processed Successfully"\n}</pre>
            
            <strong>Sample Failure Response</strong>
            <pre style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 8px; border-radius: 4px; font-family: monospace; color: #dc2626;">{\n  "status": "FAILED",\n  "errorCode": "",\n  "errorMessage": ""\n}</pre>
        </div>

        <div style="background-color: #f1f5f9; padding: 4px 8px; font-weight: bold; color: #0f172a; border-left: 3px solid #3b82f6;">5. Error Handling</div>
        <table width="100%" cellpadding="6" style="border-collapse: collapse; margin: 5px 0 15px 0; border: 1px solid #e2e8f0; text-align: left;">
            <tr style="background-color: #f8fafc;"><th style="border: 1px solid #e2e8f0;">Error Code</th><th style="border: 1px solid #e2e8f0;">Description</th><th style="border: 1px solid #e2e8f0;">Action Required</th></tr>
            <tr><td style="border: 1px solid #e2e8f0;">400</td><td style="border: 1px solid #e2e8f0;">Bad Request</td><td style="border: 1px solid #e2e8f0;">Validate Request Payload</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">401</td><td style="border: 1px solid #e2e8f0;">Unauthorized</td><td style="border: 1px solid #e2e8f0;">Verify Authentication</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">403</td><td style="border: 1px solid #e2e8f0;">Forbidden</td><td style="border: 1px solid #e2e8f0;">Check Access Permission</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">404</td><td style="border: 1px solid #e2e8f0;">API Not Found</td><td style="border: 1px solid #e2e8f0;">Verify Endpoint URL</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">408</td><td style="border: 1px solid #e2e8f0;">Request Timeout</td><td style="border: 1px solid #e2e8f0;">Retry Request</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">500</td><td style="border: 1px solid #e2e8f0;">Internal Server Error</td><td style="border: 1px solid #e2e8f0;">Contact API Team</td></tr>
        </table>

        <div style="background-color: #f1f5f9; padding: 4px 8px; font-weight: bold; color: #0f172a; border-left: 3px solid #3b82f6;">6. Integration Details</div>
        <table width="100%" cellpadding="6" style="border-collapse: collapse; margin: 5px 0 15px 0; border: 1px solid #e2e8f0; text-align: left;">
            <tr style="background-color: #f8fafc;"><th style="border: 1px solid #e2e8f0; width: 40%;">Item</th><th style="border: 1px solid #e2e8f0;">Details</th></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Timeout</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Retry Mechanism</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Retry Count</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Expected TPS</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Callback Required</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">Yes / No</td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Duplicate Request Handling</td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Correlation ID Required</td><td style="border: 1px solid #e2e8f0; color: #94a3b8;">Yes / No</td></tr>
        </table>

        <div style="background-color: #f1f5f9; padding: 4px 8px; font-weight: bold; color: #0f172a; border-left: 3px solid #3b82f6;">7. Documents Required</div>
        <ul style="margin: 5px 0 15px 0; padding-left: 25px; line-height: 1.6;">
            <li>Swagger / OpenAPI Document</li>
            <li>Postman Collection</li>
            <li>Sample Request & Response</li>
            <li>Error Code List</li>
            <li>Test Credentials</li>
        </ul>

        <div style="background-color: #f1f5f9; padding: 4px 8px; font-weight: bold; color: #0f172a; border-left: 3px solid #3b82f6;">8. Support Contact</div>
        <table width="100%" cellpadding="6" style="border-collapse: collapse; margin: 5px 0 5px 0; border: 1px solid #e2e8f0; text-align: left;">
            <tr style="background-color: #f8fafc;"><th style="border: 1px solid #e2e8f0;">Team</th><th style="border: 1px solid #e2e8f0;">Contact Person</th><th style="border: 1px solid #e2e8f0;">Email</th></tr>
            <tr><td style="border: 1px solid #e2e8f0;">API Team</td><td style="border: 1px solid #e2e8f0;"></td><td style="border: 1px solid #e2e8f0;"></td></tr>
            <tr><td style="border: 1px solid #e2e8f0;">Infra Team</td><td style="border: 1px solid #e2e8f0;"></td><td style="border: 1px solid #e2e8f0;"></td></tr>
        </table>
    </div>
    """,
    "database": """
    <ul style='margin: 10px 0 0 0; padding-left: 20px; font-size: 13px; color: #475569;'>
        <li><strong>Database Specs</strong> (Engine Type and Version)</li>
        <li><strong>Schema / ERD Diagram</strong></li>
        <li><strong>Target Objects</strong> (Views vs. Direct Table Inserts)</li>
        <li><strong>Network Firewall / IP Whitelisting requirements</strong></li>
    </ul>
    """,
    "unassigned": """
    <ul style='margin: 10px 0 0 0; padding-left: 20px; font-size: 13px; color: #475569;'>
        <li><strong>High-level business requirement document</strong></li>
        <li><strong>Known technical constraints or vendor limitations</strong></li>
    </ul>
    """
}

def send_workshop_invites():
    """Queries tomorrow's workshops and sends HTML invites to teams mapped in TeamMaster."""
    print(f"\n[{datetime.now()}] 🚀 RUNNING DAILY WORKSHOP SCHEDULER...")
    
    db = SessionLocal()
    try:
        # 1. Get TEAM_EMAILS dynamically from TeamMaster (Just like Phase 1!)
        master_teams = db.query(TeamMaster).filter(TeamMaster.is_active == True).all()
        TEAM_EMAILS = {team.team_name: team.contact_email for team in master_teams}

        # 2. Find workshops for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%B %d, %Y")
        
        results = db.query(
            IntegrationTouchpoint, IDRFunctional, IDRTechnical
        ).join(
            IDRFunctional, IntegrationTouchpoint.id == IDRFunctional.touchpoint_id
        ).join(
            IDRTechnical, IntegrationTouchpoint.id == IDRTechnical.touchpoint_id
        ).filter(
            IDRTechnical.start_date == tomorrow
        ).all()

        if not results:
            print(f"[{datetime.now()}] No workshops scheduled for {tomorrow_str}.")
            return {"status": "success", "emails_sent": 0, "message": f"No workshops scheduled for {tomorrow_str}."}

        # 3. Group workshops by team
        workshops_by_owner = defaultdict(list)
        for tp, func, tech in results:
            owner = getattr(func, "owner", "Unassigned Team")
            integration = tech.integration_type.lower() if tech.integration_type else "unassigned"
            
            workshops_by_owner[owner].append({
                "name": tp.name,
                "module": func.module or "-",
                "integration": integration.upper(),
                "reqs": PRE_REQS.get(integration, PRE_REQS["unassigned"])
            })

        # 4. Generate and send emails
        emails_sent = 0
        for team, items in workshops_by_owner.items():
            recipient_email = TEAM_EMAILS.get(team)
            
            if not recipient_email:
                print(f"[{datetime.now()}] ⚠️ Skipping {team} - No email found in TeamMaster.")
                continue

            # Generate the specific touchpoint HTML blocks
            cards_html = ""
            for item in items:
                cards_html += f"""
                <div style="border: 1px solid #cbd5e1; border-radius: 6px; margin-bottom: 20px; background-color: #ffffff; overflow: hidden;">
                    <div style="background-color: #f8fafc; padding: 12px 20px; border-bottom: 1px solid #cbd5e1;">
                        <h3 style="margin: 0; color: #0f172a; font-size: 16px;">
                            {item['name']} <span style="float: right; color: #64748b; font-size: 13px; font-weight: normal; margin-top: 2px;">Type: {item['integration']}</span>
                        </h3>
                    </div>
                    <div style="padding: 20px;">
                        <strong style="color: #3b82f6; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px;">Required Pre-Requisites</strong>
                        {item['reqs']}
                    </div>
                </div>
                """

            # Build the overall Email structure mirroring your Phase 1 styling
            html_content = f"""
            <html>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 30px 10px; margin: 0;">
                    <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-top: 4px solid #8b5cf6;">
                        
                        <div style="background-color: #1a233a; padding: 20px; text-align: center;">
                            <h2 style="color: white; margin: 0;">SDG<span style="color: #8b5cf6;">NEXT</span></h2>
                            <p style="color: #94a3b8; font-size: 12px; margin-top: 5px; text-transform: uppercase;">Architecture Workshop Invite</p>
                        </div>

                        <div style="padding: 35px 40px;">
                            <h2 style="margin: 0 0 20px 0; color: #0f172a; font-size: 22px;">Action Required: Workshop Tomorrow</h2>
                            
                            <div style="color: #334155; font-size: 15px; line-height: 1.6; margin-bottom: 30px;">
                                Hello <strong>{team}</strong> Team,<br><br>
                                This is an automated briefing to confirm your Technical Architecture Workshop scheduled for tomorrow, <strong>{tomorrow_str}</strong>. To ensure a productive session, please review the touchpoints below and come prepared with the listed architectural prerequisites.
                            </div>
                            
                            {cards_html}
                            
                            <div style="margin-top: 35px; text-align: center;">
                                <a href="http://127.0.0.1:8000" style="background-color: #0f172a; color: white; text-decoration: none; padding: 12px 26px; border-radius: 6px; font-size: 14px; font-weight: 600; display: inline-block;">Open Command Center</a>
                            </div>
                        </div>
                    </div>
                </body>
            </html>
            """

            # Send Email
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"📅 Action Required: Architecture Workshop Tomorrow ({tomorrow_str})"
            msg["From"] = SMTP_USERNAME
            msg["To"] = recipient_email

            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(SMTP_USERNAME, recipient_email, msg.as_string())
                
            print(f"[{datetime.now()}] ✅ Workshop Invite sent to {team} ({recipient_email}).")
            emails_sent += 1

        return {"status": "success", "emails_sent": emails_sent, "message": "Invites sent successfully."}

    except Exception as e:
        print(f"[{datetime.now()}] 🚨 Failed to send workshop invites: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()