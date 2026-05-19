import smtplib
import uuid
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


def _parse_mom_msg_id(log):
    """Extract Message-ID from a MOM_SENT log comment.

    Returns None if absent (e.g., legacy logs from before Message-ID
    was captured in the comment).
    """
    if not log or not log.comment:
        return None
    for part in log.comment.split(";"):
        if part.startswith("MSG_ID="):
            return part.split("=", 1)[1]
    return None

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


def send_touchpoint_mom(touchpoint_id: int, html_body: str, override_recipients: list = None, write_action_log: bool = True) -> dict:
    """Sends a touchpoint-level MoM email to derived or overridden recipients.

    Args:
        write_action_log: If True (default), inserts IDRActionLog and commits.
            Set to False when the caller manages its own transaction (atomicity).
    """
    from app.models.domain import IntegrationTouchpoint, IDRFunctional, IDRTechnical, IDRActionLog
    from app.services.identity_validator import resolve_member_email_and_cc

    db = SessionLocal()
    try:
        tp = db.query(IntegrationTouchpoint).filter(
            IntegrationTouchpoint.id == touchpoint_id
        ).first()
        if not tp:
            return {"sent_to": [], "skipped": ["Touchpoint not found"], "success": False}

        project_id = tp.project_id
        func = db.query(IDRFunctional).filter(
            IDRFunctional.touchpoint_id == touchpoint_id
        ).first()
        tech = db.query(IDRTechnical).filter(
            IDRTechnical.touchpoint_id == touchpoint_id
        ).first()

        if override_recipients:
            to_emails = [e.strip() for e in override_recipients if e.strip()]
            cc_emails = []
            skipped = []
        else:
            to_emails = []
            cc_emails = []
            skipped = []
            names_to_resolve = []

            if func:
                if func.owner:
                    names_to_resolve.append(func.owner)
                if func.technical_owner:
                    names_to_resolve.append(func.technical_owner)
                if func.pending_with:
                    names_to_resolve.append(func.pending_with)
            if tech and tech.pending_with:
                names_to_resolve.append(tech.pending_with)

            for name in set(names_to_resolve):
                to_email, cc_email, display = resolve_member_email_and_cc(
                    db, name, project_id=project_id
                )
                if to_email:
                    to_emails.append(to_email)
                    if cc_email:
                        cc_emails.append(cc_email)
                else:
                    skipped.append(name)

            to_emails = list(set(to_emails))
            cc_emails = list(set(cc_emails) - set(to_emails))

        if not to_emails:
            return {"sent_to": [], "skipped": skipped, "success": False}

        today_str = datetime.now().strftime("%B %d, %Y")
        tp_name = tp.name or "Integration Touchpoint"

        final_html = (
            "<html><body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;"
            "color:#1e293b;background:#f8fafc;padding:30px;'>"
            "<div style='max-width:800px;margin:0 auto;background:white;border-radius:8px;"
            "box-shadow:0 4px 6px rgba(0,0,0,0.05);overflow:hidden;border-top:5px solid #4338ca;'>"
            f"<div style='padding:30px;background:#f1f5f9;border-bottom:1px solid #e2e8f0;'>"
            f"<h2 style='margin:0;color:#0f172a;'>Minutes of Meeting</h2>"
            f"<p style='margin:5px 0 0;color:#64748b;font-size:14px;'>"
            f"{tp_name} &mdash; {today_str}</p></div>"
            f"<div style='padding:40px;line-height:1.6;font-size:15px;'>{html_body}</div>"
            "<div style='padding:20px;text-align:center;background:#f8fafc;"
            "border-top:1px solid #e2e8f0;font-size:12px;color:#94a3b8;'>"
            "Automated MoM via <strong>SDGNext Command Center</strong></div>"
            "</div></body></html>"
        )

                # Generate stable Message-ID for threading
        msg_id = f"<mom-{touchpoint_id}-{uuid.uuid4().hex[:8]}@sdgnext.local>"

        msg = MIMEMultipart("alternative")
        msg["Message-ID"] = msg_id
        # CRITICAL: Subject is date-free to enable threading of subsequent
        # MoM-pointer nudges. Date is communicated in the email body.
        msg["Subject"] = f"MoM: {tp_name}"
        msg["From"] = SMTP_USERNAME
        msg["To"] = ", ".join(to_emails)
        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)
        msg.attach(MIMEText(final_html, "html"))

        envelope = list(set(to_emails + cc_emails))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_USERNAME, envelope, msg.as_string())

                # Only write action log + commit if caller hasn't taken ownership
        if write_action_log:
            recipient_count = len(to_emails) + len(cc_emails)
            db.add(IDRActionLog(
                touchpoint_id=touchpoint_id,
                action_type="MOM_SENT",
                action_by="User",
                comment=f"MoM emailed to {recipient_count} recipients;MSG_ID={msg_id}"
            ))
            db.commit()

        print(f"[{datetime.now()}] MoM sent for TP {touchpoint_id} to {to_emails}")
        return {"sent_to": to_emails, "skipped": skipped, "success": True, "msg_id": msg_id}

    except Exception as e:
        print(f"[{datetime.now()}] Failed to send touchpoint MoM: {e}")
        return {"sent_to": [], "skipped": [str(e)], "success": False, "msg_id": None}
    finally:
        db.close()