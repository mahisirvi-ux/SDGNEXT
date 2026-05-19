import smtplib
import uuid
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


def _parse_invited_date(log):
    """Extract workshop date from WORKSHOP_INVITE_SENT log comment."""
    if not log or not log.comment:
        return None
    for part in log.comment.split(";"):
        if part.startswith("WORKSHOP_DATE="):
            iso = part.split("=", 1)[1]
            try:
                return date.fromisoformat(iso)
            except ValueError:
                return None
    return None


def _parse_invite_msg_id(log):
    """Extract email Message-ID from WORKSHOP_INVITE_SENT log comment."""
    if not log or not log.comment:
        return None
    for part in log.comment.split(";"):
        if part.startswith("MSG_ID="):
            return part.split("=", 1)[1]
    return None


def _build_thread_headers(db, items):
    """Build RFC 5322 threading headers from prior WORKSHOP_INVITE_SENT logs.

    Returns (in_reply_to, references_chain) or (None, None) if no prior
    thread exists for this department.

    Per RFC 5322 \'a73.6.4:
      - References: space-separated list of ALL prior Message-IDs in the
        thread, ordered oldest-first. Gmail and Outlook use this to
        reconstruct the full conversation tree.
      - In-Reply-To: the single most-recent Message-ID this email is
        directly replying to.

    Since each department email maps to one logical thread (all workshop
    invites for the same project+department thread together), we collect
    ALL prior MSG_IDs from WORKSHOP_INVITE_SENT logs for the touchpoints
    in this group, deduplicated and ordered by created_at ascending.

    Note: touchpoint IDs are globally unique (auto-increment PK), so
    filtering by tp_ids that came from a project-scoped query is
    sufficient project scoping. No extra project_id filter needed.
    """
    tp_ids = [item["tp_id"] for item in items]
    prior_logs = db.query(IDRActionLog).filter(
        IDRActionLog.touchpoint_id.in_(tp_ids),
        IDRActionLog.action_type == "WORKSHOP_INVITE_SENT"
    ).order_by(IDRActionLog.created_at.asc()).all()

    msg_ids = []
    for log in prior_logs:
        mid = _parse_invite_msg_id(log)
        if mid and mid not in msg_ids:
            msg_ids.append(mid)

    if not msg_ids:
        return None, None

    in_reply_to = msg_ids[-1]
    references_chain = " ".join(msg_ids)
    return in_reply_to, references_chain


def send_workshop_invites(project_id: int):
    """Sends department-wise workshop invites for TOMORROW's scheduled sessions.

    Project-scoped. Implements reschedule detection. Rescheduled invites
    thread with the original via In-Reply-To/References headers and a
    stable (date-free) subject line.
    """
    print(f"\n[{datetime.now()}] Running workshop invites for project_id={project_id}...")
    db = SessionLocal()
    try:
        return _run_invites(db, project_id)
    except Exception as e:
        print(f"[{datetime.now()}] Failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def _run_invites(db, project_id):
    """Core invite logic."""
    # 1. Identity lookup
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

    # 2. Query tomorrow's workshops
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%B %d, %Y")
    tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
    day_after_start = tomorrow_start + timedelta(days=1)

    results = db.query(
        IntegrationTouchpoint, IDRFunctional, IDRTechnical
    ).join(
        IDRTechnical, IntegrationTouchpoint.id == IDRTechnical.touchpoint_id
    ).outerjoin(
        IDRFunctional, IntegrationTouchpoint.id == IDRFunctional.touchpoint_id
    ).filter(
        IntegrationTouchpoint.project_id == project_id,
        IDRTechnical.start_date >= tomorrow_start,
        IDRTechnical.start_date < day_after_start,
        IDRTechnical.tech_status.notin_(["Completed", "Document Review", "Pending Document"])
    ).order_by(IDRTechnical.start_date.asc()).all()

    print(f"[{datetime.now()}] Query returned {len(results)} touchpoint(s) for tomorrow.")
    for tp, func, tech in results:
        ow = func.owner if func else "NO_FUNC_ROW"
        print(f"  - \'{tp.name}\' | owner=\'{ow}\' | status=\'{tech.tech_status}\' | start={tech.start_date}")

    if not results:
        msg = f"No workshops scheduled for {tomorrow_str} in this project."
        print(f"[{datetime.now()}] {msg}")
        return {"status": "success", "emails_sent": 0, "skipped_duplicates": 0,
                "rescheduled_count": 0, "message": msg}

    # 3. Group by department + reschedule detection
    dept_groups = {}
    unmapped_names = set()
    skipped_count = 0
    rescheduled_count = 0

    for tp, func, tech in results:
        owner_raw = (getattr(func, "owner", None) or "").strip() if func else ""
        tech_owner_raw = (getattr(func, "technical_owner", None) or "").strip() if func else ""
        mod_owner_raw = (getattr(func, "module_owner_functional", None) or "").strip() if func else ""

        owner_identity = person_lookup.get(owner_raw.lower()) if owner_raw else None
        if not owner_identity:
            if owner_raw:
                unmapped_names.add(owner_raw)
                print(f"[{datetime.now()}] SKIP \'{tp.name}\': owner \'{owner_raw}\' not in team_master")
            else:
                print(f"[{datetime.now()}] SKIP \'{tp.name}\': no owner (missing IDRFunctional?)")
            continue

        # Reschedule detection
        current_date = tech.start_date.date()
        last_log = db.query(IDRActionLog).filter(
            IDRActionLog.touchpoint_id == tp.id,
            IDRActionLog.action_type == "WORKSHOP_INVITE_SENT"
        ).order_by(IDRActionLog.created_at.desc()).first()

        prior_date = _parse_invited_date(last_log)

        if prior_date is None:
            invite_kind = "fresh"
        elif prior_date == current_date and tech.tech_status != "Rescheduled":
            invite_kind = "duplicate"
        else:
            invite_kind = "rescheduled"

        print(f"[{datetime.now()}] \'{tp.name}\': prior={prior_date}, "
              f"current={current_date}, status={tech.tech_status} -> {invite_kind}")

        if invite_kind == "duplicate":
            skipped_count += 1
            continue
        if invite_kind == "rescheduled":
            rescheduled_count += 1

        # Department grouping
        dept_id = owner_identity["dept_id"]
        if dept_id not in dept_groups:
            dept_groups[dept_id] = {
                "dept_name": owner_identity["dept_name"],
                "dept_email": owner_identity["dept_email"],
                "owner_names": set(), "owner_emails": set(),
                "crm_names": set(), "crm_emails": set(),
                "items": [],
            }

        grp = dept_groups[dept_id]
        grp["owner_names"].add(owner_identity["display_name"])
        grp["owner_emails"].add(owner_identity["person_email"])

        if tech_owner_raw:
            ti = person_lookup.get(tech_owner_raw.lower())
            if ti:
                grp["crm_names"].add(ti["display_name"])
                grp["crm_emails"].add(ti["person_email"])
        if mod_owner_raw:
            mi = person_lookup.get(mod_owner_raw.lower())
            if mi:
                grp["crm_names"].add(mi["display_name"])
                grp["crm_emails"].add(mi["person_email"])

        time_window = _fmt_time(tech)
        prior_date_str = None
        if invite_kind == "rescheduled" and prior_date:
            prior_date_str = prior_date.strftime("%B %d, %Y")

        grp["items"].append({
            "name": tp.name, "tp_id": tp.id,
            "module": (func.module if func else None) or "-",
            "owner": owner_identity["display_name"],
            "integration": (tech.integration_type or "unassigned").upper(),
            "tech_owner": tech_owner_raw or "-",
            "functional_owner": mod_owner_raw or "-",
            "time_window": time_window,
            "invite_kind": invite_kind,
            "prior_date_str": prior_date_str,
            "workshop_date_iso": current_date.isoformat(),
        })

    for name in unmapped_names:
        print(f"[{datetime.now()}] Owner \'{name}\' not in team_master.")

    # 4. Send per department
    emails_sent = 0
    for dept_id, grp in dept_groups.items():
        if _send_dept_email(db, project_id, dept_id, grp, tomorrow, tomorrow_str):
            emails_sent += 1

    # Response
    parts = []
    if emails_sent > 0:
        parts.append(f"Invites sent for {emails_sent} department(s)")
    if rescheduled_count > 0:
        parts.append(f"{rescheduled_count} marked as rescheduled")
    if skipped_count > 0:
        parts.append(f"skipped {skipped_count} already-invited touchpoint(s)")
    message = ". ".join(parts) + "." if parts else "No invites sent."

    return {"status": "success", "emails_sent": emails_sent,
            "skipped_duplicates": skipped_count,
            "rescheduled_count": rescheduled_count, "message": message}


def _fmt_time(tech):
    """Format time window string."""
    if not tech.start_date:
        return ""
    s = tech.start_date.strftime("%I:%M %p").lstrip("0")
    if tech.end_date:
        e = tech.end_date.strftime("%I:%M %p").lstrip("0")
        return f"{s} \u2013 {e}"
    return s


def _send_dept_email(db, project_id, dept_id, grp, tomorrow, tomorrow_str):
    """Send one department's workshop invite email. Returns True on success.

    Threading strategy:
    - Subject is date-free and stable per (project, department) so Gmail
      groups all invites for the same dept into one conversation.
    - In-Reply-To and References are set from prior WORKSHOP_INVITE_SENT
      logs for ALL emails (not just rescheduled), so even newly-added
      touchpoints thread into the existing conversation.
    """
    dept_name = grp["dept_name"]
    dept_email = grp["dept_email"]
    items = grp["items"]
    if not items:
        return False

    all_to = set(grp["owner_emails"]) | set(grp["crm_emails"])
    if not all_to:
        print(f"[{datetime.now()}] No To emails for \'{dept_name}\'. Skip.")
        return False

    bank_str = ", ".join(sorted(grp["owner_names"]))
    crm_str = ", ".join(sorted(grp["crm_names"])) if grp["crm_names"] else "\u2014"

    resched_items = [i for i in items if i.get("invite_kind") == "rescheduled"]
    has_resched = len(resched_items) > 0

    # CRITICAL: Subject is intentionally date-free. Gmail threads emails
    # by normalized subject + Message-ID references. If the subject
    # changes (e.g., when a workshop date changes on reschedule), Gmail
    # starts a NEW conversation regardless of In-Reply-To/References
    # headers. Keep this string stable per (project, department).
    subject = f"\U0001f4c5 Workshop Invite \u2013 {dept_name}"

    # HTML content
    banner = _build_banner(resched_items)
    participants = _participants_html(dept_name, bank_str, crm_str)
    table = _touchpoint_table(items)
    html = _full_html(tomorrow_str, len(items), banner, participants, table)

    # Compose message
    msg_id = f"<workshop-{dept_id}-{tomorrow.isoformat()}-{uuid.uuid4().hex[:8]}@sdgnext.local>"
    msg = MIMEMultipart("alternative")
    msg["Message-ID"] = msg_id
    msg["Subject"] = subject
    msg["From"] = SMTP_USERNAME
    msg["To"] = ", ".join(sorted(all_to))
    if dept_email and dept_email not in all_to:
        msg["Cc"] = dept_email

    # Threading: apply to EVERY email that has prior logs for this dept,
    # not just rescheduled ones. This ensures new touchpoints added to
    # an existing department's workshop also thread correctly.
    in_reply_to, references_chain = _build_thread_headers(db, items)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references_chain:
        msg["References"] = references_chain

    msg.attach(MIMEText(html, "html"))

    # Send
    envelope = list(all_to)
    if dept_email and dept_email not in all_to:
        envelope.append(dept_email)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, envelope, msg.as_string())

    # Post-send: status update + action logs
    for item in items:
        tp_id = item.get("tp_id")
        if not tp_id:
            continue
        tech_rec = db.query(IDRTechnical).filter(
            IDRTechnical.touchpoint_id == tp_id
        ).first()
        if tech_rec and tech_rec.tech_status not in ["Completed", "Document Review", "Pending Document"]:
            tech_rec.tech_status = "Scheduled"
        db.add(IDRActionLog(
            touchpoint_id=tp_id,
            action_type="WORKSHOP_INVITE_SENT",
            action_by="System (Workshop Mailer)",
            comment=(
                f"WORKSHOP_DATE={item['workshop_date_iso']};"
                f"KIND={item['invite_kind']};"
                f"RECIPIENTS_COUNT={len(envelope)};"
                f"MSG_ID={msg_id}"
            )
        ))
    db.commit()

    disp = ", ".join(sorted(grp["owner_names"] | grp["crm_names"]))
    print(f"[{datetime.now()}] Sent for \'{dept_name}\' ({len(items)} tp) -> {disp}")
    return True


def _build_banner(resched_items):
    """Yellow reschedule warning banner for email body."""
    if not resched_items:
        return ""
    rows = ""
    for r in resched_items:
        prior = r.get("prior_date_str") or "a previous time"
        rows += (f"<li><strong>{r['name']}</strong> \u2014 "
                 f"previously scheduled for {prior}, now {r['time_window']}</li>")
    return (
        '<div style="background-color:#fef3c7;border-left:4px solid #f59e0b;'
        'padding:12px 16px;margin:0 0 20px 0;border-radius:4px;">'
        '<p style="margin:0 0 8px 0;font-weight:600;color:#92400e;">'
        '\u26a0\ufe0f The following workshops have been RESCHEDULED:</p>'
        '<ul style="margin:0;padding-left:20px;color:#78350f;'
        f'font-size:13px;line-height:1.6;">{rows}</ul></div>'
    )


def _participants_html(dept_name, bank_str, crm_str):
    """Blue participants info block."""
    return (
        '<div style="background-color:#f0f9ff;border:1px solid #bae6fd;'
        'border-radius:6px;padding:16px 20px;margin-bottom:25px;">'
        '<div style="font-size:11px;font-weight:bold;color:#0369a1;'
        'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px;">'
        'Workshop Participants</div>'
        '<table style="width:100%;font-size:13px;color:#334155;">'
        f'<tr><td style="padding:4px 0;font-weight:600;width:160px;">{dept_name}:</td>'
        f'<td style="padding:4px 0;">{bank_str}</td></tr>'
        '<tr><td style="padding:4px 0;font-weight:600;">CRM / Technical Team:</td>'
        f'<td style="padding:4px 0;">{crm_str}</td></tr>'
        '</table></div>'
    )


def _touchpoint_table(items):
    """Touchpoint summary table HTML."""
    rows = ""
    for item in items:
        rows += (
            '<tr>'
            f'<td style="border:1px solid #e2e8f0;padding:10px 12px;font-size:13px;font-weight:600;color:#0f172a;">{item["name"]}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:10px 12px;font-size:13px;color:#334155;">{item["module"]}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:10px 12px;font-size:13px;color:#334155;">{item["integration"]}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:10px 12px;font-size:13px;color:#334155;">{item["owner"]}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:10px 12px;font-size:13px;color:#334155;">{item["tech_owner"]}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:10px 12px;font-size:13px;color:#334155;">{item["functional_owner"]}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:10px 12px;font-size:13px;font-weight:600;color:#4338ca;">{item["time_window"]}</td>'
            '</tr>'
        )
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">'
        '<thead><tr style="background-color:#f1f5f9;">'
        '<th style="border:1px solid #e2e8f0;padding:10px 12px;font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;text-align:left;">Touchpoint</th>'
        '<th style="border:1px solid #e2e8f0;padding:10px 12px;font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;text-align:left;">Module</th>'
        '<th style="border:1px solid #e2e8f0;padding:10px 12px;font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;text-align:left;">Type</th>'
        '<th style="border:1px solid #e2e8f0;padding:10px 12px;font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;text-align:left;">Owner</th>'
        '<th style="border:1px solid #e2e8f0;padding:10px 12px;font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;text-align:left;">Technical Owner</th>'
        '<th style="border:1px solid #e2e8f0;padding:10px 12px;font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;text-align:left;">Functional Owner</th>'
        '<th style="border:1px solid #e2e8f0;padding:10px 12px;font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;text-align:left;">Time</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
    )


def _full_html(tomorrow_str, item_count, banner, participants, table):
    """Assemble the full email HTML document."""
    return (
        '<html><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;'
        'color:#1e293b;background-color:#f8fafc;padding:30px 10px;margin:0;">'
        '<div style="max-width:700px;margin:0 auto;background:white;border-radius:10px;'
        'overflow:hidden;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);border-top:4px solid #8b5cf6;">'
        '<div style="background-color:#1a233a;padding:20px;text-align:center;">'
        '<h2 style="color:white;margin:0;">SDG<span style="color:#8b5cf6;">NEXT</span></h2>'
        '<p style="color:#94a3b8;font-size:12px;margin-top:5px;text-transform:uppercase;">'
        'Architecture Workshop Invite</p></div>'
        '<div style="padding:35px 40px;">'
        '<h2 style="margin:0 0 20px 0;color:#0f172a;font-size:22px;">'
        'Action Required: Workshop Tomorrow</h2>'
        '<div style="color:#334155;font-size:15px;line-height:1.6;margin-bottom:25px;">'
        f'Hello <strong>Team</strong>,<br><br>'
        'This is an automated briefing to confirm your Technical Architecture Workshop '
        f'scheduled for tomorrow, <strong>{tomorrow_str}</strong>. '
        f'Please review the <strong>{item_count} touchpoint(s)</strong> below and come '
        'prepared with the listed architectural prerequisites.</div>'
        f'{banner}'
        f'{participants}'
        f'{table}'
        '</div></div></body></html>'
    )
