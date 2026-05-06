import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

from app.core.ai_agent import generate_project_mom
from app.core.database import SessionLocal
from app.models.domain import IDRFunctional, IntegrationTouchpoint, IDRActionLog

# --- CONFIGURATION (Keep consistent with email_engine.py) ---
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
SMTP_USERNAME = "mahi.sirvi@gmail.com"
SMTP_PASSWORD = "klrynpcgevlubkfj" 
MOM_RECIPIENTS = ["mahi.sirvi@gmail.com", "rahulnikam5050@gmail.com"] # Add PMO/Leadership emails here

def generate_and_send_mom():
    """Gathers the last 48 hours of discussions and sends an AI-generated MOM."""
    db = SessionLocal()
    try:
        print(f"[{datetime.now()}] Generating Automated MOM in the background...")
        
        # 1. Define the timeframe (e.g., gather logs from the last 2 days)
        time_threshold = datetime.now() - timedelta(days=2)

        # 2. Fetch all touchpoints that had activity in the last 48 hours
        recent_logs = db.query(IDRActionLog, IntegrationTouchpoint, IDRFunctional).join(
            IntegrationTouchpoint, IDRActionLog.touchpoint_id == IntegrationTouchpoint.id
        ).join(
            IDRFunctional, IntegrationTouchpoint.id == IDRFunctional.touchpoint_id
        ).filter(
            IDRActionLog.created_at >= time_threshold
        ).order_by(IDRActionLog.created_at.desc()).all()

        if not recent_logs:
            print(f"[{datetime.now()}] No recent activity found in the last 48 hours. Skipping MOM.")
            return

        # 3. Format the raw data for the AI to read
        raw_data_dump = ""
        for log, tp, func in recent_logs:
            date_str = log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else "Unknown"
            pointer = log.open_pointer_history or "None"
            comment = log.comment or "None"
            
            raw_data_dump += f"""
            [Date: {date_str}] 
            - Touchpoint: {tp.name or 'Unknown'} (Module: {func.module or 'Unknown'})
            - Pending With: {func.pending_with or 'Unassigned'}
            - Discussion/Comment: {comment}
            - Open Pointer/Blocker: {pointer}
            -------------------------
            """

        # 4. Feed it to the AI to write the MOM
        print(f"[{datetime.now()}] Sending {len(recent_logs)} records to AI Agent for MOM synthesis...")
        mom_html_body = generate_project_mom(raw_data_dump)

        # 5. Wrap the AI's output in your branded email template
        today_str = datetime.now().strftime("%B %d, %Y")
        final_email_html = f"""
        <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 30px;">
                <div style="max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); overflow: hidden; border-top: 5px solid #0ea5e9;">
                    <div style="padding: 30px; background-color: #f1f5f9; border-bottom: 1px solid #e2e8f0;">
                        <h2 style="margin: 0; color: #0f172a;">Minutes of Meeting / Project Status</h2>
                        <p style="margin: 5px 0 0 0; color: #64748b; font-size: 14px;">Generated on: {today_str}</p>
                    </div>
                    
                    <div style="padding: 40px; line-height: 1.6; font-size: 15px;">
                        {mom_html_body}
                    </div>
                    
                    <div style="padding: 20px; text-align: center; background-color: #f8fafc; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8;">
                        Automated PMO Briefing via <strong>SDGNext Command Center</strong>
                    </div>
                </div>
            </body>
        </html>
        """

        # 6. Send the MOM to the Project Leadership
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📑 Automated Project MOM - {today_str}"
        msg["From"] = SMTP_USERNAME
        msg["To"] = ", ".join(MOM_RECIPIENTS)

        msg.attach(MIMEText(final_email_html, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_USERNAME, MOM_RECIPIENTS, msg.as_string())
            
        print(f"[{datetime.now()}] ✅ Automated MOM sent successfully to stakeholders.")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Failed to generate MOM: {e}")
    finally:
        db.close()