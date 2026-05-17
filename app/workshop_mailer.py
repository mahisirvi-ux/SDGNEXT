import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, timedelta, datetime
from collections import defaultdict
from app.core.database import SessionLocal
from app.models.domain import IntegrationTouchpoint, IDRFunctional, IDRTechnical, TeamMaster, DepartmentMaster, IDRActionLog

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
    """Sends department-wise workshop invites for TOMORROW's scheduled sessions.

    Runs one day prior to the workshop. If workshops are scheduled for tomorrow,
    sends one email per department with all touchpoints and timings.

    Recipients:
      TO:  All bank-side owners from that department
           + Technical Owner (CRM)
           + Module Owner (Functional)
      CC:  Department group email
    """
    print(f"\n[{datetime.now()}] 🚀 RUNNING DAILY WORKSHOP SCHEDULER...")

    db = SessionLocal()
    try:
        # 1. Build identity lookup: name_lower -> {email, dept_id, dept_email, dept_name}
        identity_rows = db.query(TeamMaster, DepartmentMaster).join(
            DepartmentMaster, TeamMaster.dept_id == DepartmentMaster.dept_id
        ).filter(TeamMaster.is_active == True).all()

        person_lookup = {}
        for m, d in identity_rows:
            person_lookup[m.full_name.strip().lower()] = {
                "person_email": m.email,
                "dept_id": d.dept_id,
                "dept_email": d.department_email,
                "dept_name": d.department_name,
                "display_name": m.full_name,
            }

        # 2. Send invites strictly for TOMORROW's workshops only
        tomorrow = date.today() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%B %d, %Y")
        tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
        day_after_start = tomorrow_start + timedelta(days=1)

        results = db.query(
            IntegrationTouchpoint, IDRFunctional, IDRTechnical
        ).join(
            IDRFunctional, IntegrationTouchpoint.id == IDRFunctional.touchpoint_id
        ).join(
            IDRTechnical, IntegrationTouchpoint.id == IDRTechnical.touchpoint_id
        ).filter(
            IDRTechnical.start_date >= tomorrow_start,
            IDRTechnical.start_date < day_after_start
        ).order_by(IDRTechnical.start_date.asc()).all()

        if not results:
            print(f"[{datetime.now()}] No workshops scheduled for {tomorrow_str}.")
            return {"status": "success", "emails_sent": 0, "message": f"No workshops scheduled for {tomorrow_str}."}

        # 3. Group workshops by the OWNER'S DEPARTMENT
        #    Key = dept_id (or 'UNMAPPED' for owners not in team_master)
        dept_groups = {}  # dept_id -> { dept_name, dept_email, owner_emails, crm_emails, items }

        unmapped_names = set()

        for tp, func, tech in results:
            owner_raw = (getattr(func, "owner", None) or "").strip()
            tech_owner_raw = (getattr(func, "technical_owner", None) or "").strip()
            mod_owner_raw = (getattr(func, "module_owner_functional", None) or "").strip()

            # Resolve the owner to find their department
            owner_identity = person_lookup.get(owner_raw.lower()) if owner_raw else None

            if not owner_identity:
                # Owner not mapped in team_master — log warning and skip this touchpoint
                if owner_raw:
                    unmapped_names.add(owner_raw)
                continue

            dept_id = owner_identity["dept_id"]

            # Initialize the department group if first time seeing it
            if dept_id not in dept_groups:
                dept_groups[dept_id] = {
                    "dept_name": owner_identity["dept_name"],
                    "dept_email": owner_identity["dept_email"],
                    "owner_names": set(),       # Bank-side owner display names
                    "owner_emails": set(),      # Bank-side owner personal emails
                    "crm_names": set(),         # Technical + Module owners (CRM side)
                    "crm_emails": set(),        # Their emails
                    "items": [],
                }

            group = dept_groups[dept_id]

            # Add the bank-side owner
            group["owner_names"].add(owner_identity["display_name"])
            group["owner_emails"].add(owner_identity["person_email"])

            # Resolve Technical Owner (CRM-side) and add to To list
            if tech_owner_raw:
                tech_identity = person_lookup.get(tech_owner_raw.lower())
                if tech_identity:
                    group["crm_names"].add(tech_identity["display_name"])
                    group["crm_emails"].add(tech_identity["person_email"])

            # Resolve Module Owner (Functional) and add to To list
            if mod_owner_raw:
                mod_identity = person_lookup.get(mod_owner_raw.lower())
                if mod_identity:
                    group["crm_names"].add(mod_identity["display_name"])
                    group["crm_emails"].add(mod_identity["person_email"])

            # Build the touchpoint item for the email body
            integration = tech.integration_type.lower() if tech.integration_type else "unassigned"

            time_window = ""
            if tech.start_date:
                start_fmt = tech.start_date.strftime("%I:%M %p").lstrip("0")
                if tech.end_date:
                    end_fmt = tech.end_date.strftime("%I:%M %p").lstrip("0")
                    time_window = f"{start_fmt} – {end_fmt}"
                else:
                    time_window = start_fmt

            group["items"].append({
                "name": tp.name,
                "tp_id": tp.id,
                "module": func.module or "-",
                "owner": owner_identity["display_name"],
                "integration": integration.upper(),
                "tech_owner": tech_owner_raw or "-",
                "functional_owner": mod_owner_raw or "-",
                "time_window": time_window,
            })

        # Log unmapped owners
        for name in unmapped_names:
            print(f"[{datetime.now()}] ⚠️ Skipping owner '{name}' — not found in team_master.")

        # 4. Send ONE email per department
        emails_sent = 0
        for dept_id, group in dept_groups.items():
            dept_name = group["dept_name"]
            dept_email = group["dept_email"]
            items = group["items"]

            # Build TO list: all bank owners + technical/module owners (de-duped)
            all_to_emails = set()
            all_to_emails.update(group["owner_emails"])
            all_to_emails.update(group["crm_emails"])

            if not all_to_emails:
                print(f"[{datetime.now()}] ⚠️ No valid To emails for department '{dept_name}'. Skipping.")
                continue

            # Build the participants info block
            bank_owners_str = ", ".join(sorted(group["owner_names"]))
            crm_owners_str = ", ".join(sorted(group["crm_names"])) if group["crm_names"] else "—"

            participants_html = f"""
            <div style="background-color: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 16px 20px; margin-bottom: 25px;">
                <div style="font-size: 11px; font-weight: bold; color: #0369a1; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;">Workshop Participants</div>
                <table style="width: 100%; font-size: 13px; color: #334155;">
                    <tr>
                        <td style="padding: 4px 0; font-weight: 600; width: 160px;">{dept_name}:</td>
                        <td style="padding: 4px 0;">{bank_owners_str}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; font-weight: 600;">CRM / Technical Team:</td>
                        <td style="padding: 4px 0;">{crm_owners_str}</td>
                    </tr>
                </table>
            </div>
            """

            # Build touchpoint summary table
            table_rows = ""
            for item in items:
                table_rows += f"""
                    <tr>
                        <td style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 13px; font-weight: 600; color: #0f172a;">{item['name']}</td>
                        <td style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 13px; color: #334155;">{item['module']}</td>
                        <td style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 13px; color: #334155;">{item['integration']}</td>
                        <td style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 13px; color: #334155;">{item['owner']}</td>
                        <td style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 13px; color: #334155;">{item['tech_owner']}</td>
                        <td style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 13px; color: #334155;">{item['functional_owner']}</td>
                        <td style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 13px; font-weight: 600; color: #4338ca;">{item['time_window']}</td>
                    </tr>"""

            cards_html = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
                <thead>
                    <tr style="background-color: #f1f5f9;">
                        <th style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; text-align: left;">Touchpoint</th>
                        <th style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; text-align: left;">Module</th>
                        <th style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; text-align: left;">Type</th>
                        <th style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; text-align: left;">Owner</th>
                        <th style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; text-align: left;">Technical Owner</th>
                        <th style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; text-align: left;">Functional Owner</th>
                        <th style="border: 1px solid #e2e8f0; padding: 10px 12px; font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; text-align: left;">Time</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
            """

            # Build the full email HTML
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

                            <div style="color: #334155; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">
                                Hello <strong>Team</strong>,<br><br>
                                This is an automated briefing to confirm your Technical Architecture Workshop scheduled for tomorrow, <strong>{tomorrow_str}</strong>.
                                Please review the <strong>{len(items)} touchpoint(s)</strong> below and come prepared with the listed architectural prerequisites.
                            </div>

                            {participants_html}

                            {cards_html}                            
                        </div>
                    </div>
                </body>
            </html>
            """

            # Compose the email
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"📅 Workshop Tomorrow ({tomorrow_str}): {len(items)} Touchpoints – {dept_name}"
            msg["From"] = SMTP_USERNAME
            msg["To"] = ", ".join(sorted(all_to_emails))
            # Only CC dept_email if it's not already in the To list
            if dept_email and dept_email not in all_to_emails:
                msg["Cc"] = dept_email

            msg.attach(MIMEText(html_content, "html"))

                        # Envelope recipients = To + CC (for SMTP delivery)
            envelope_recipients = list(all_to_emails)
            if dept_email and dept_email not in all_to_emails:
                envelope_recipients.append(dept_email)

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(SMTP_USERNAME, envelope_recipients, msg.as_string())

            # Update status to 'Scheduled' for all touchpoints in this batch
            for item in items:
                tp_id = item.get("tp_id")
                if tp_id:
                    tech_rec = db.query(IDRTechnical).filter(IDRTechnical.touchpoint_id == tp_id).first()
                    if tech_rec and tech_rec.tech_status not in ["Completed", "Document Review", "Pending Document"]:
                        tech_rec.tech_status = "Scheduled"
            db.commit()

            to_list_display = ", ".join(sorted(group["owner_names"] | group["crm_names"]))
            print(f"[{datetime.now()}] ✅ Workshop Invite sent for dept '{dept_name}' "
                  f"({len(items)} touchpoints) → To: {to_list_display}, CC: {dept_email}")
            emails_sent += 1

        return {"status": "success", "emails_sent": emails_sent, "message": f"Invites sent for {emails_sent} department(s)."}

    except Exception as e:
        print(f"[{datetime.now()}] 🚨 Failed to send workshop invites: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()