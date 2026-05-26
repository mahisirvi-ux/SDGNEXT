import uuid
from datetime import date, timedelta, datetime
from collections import defaultdict
from app.core.database import SessionLocal
from app.models.domain import IntegrationTouchpoint, IDRFunctional, IDRTechnical, TeamMaster, DepartmentMaster, IDRActionLog, Project
from app.core.graph_mailer import send_graph_email, build_threading_headers, create_teams_meeting, find_sent_message, reply_to_sent_message

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
def _parse_graph_msg_id(log):
    """Extract Graph message ID from WORKSHOP_INVITE_SENT log comment.
    Returns None if absent (legacy logs won't have it)."""
    if not log or not log.comment:
        return None
    for part in log.comment.split(";"):
        if part.startswith("GRAPH_MSG_ID="):
            val = part.split("=", 1)[1].strip()
            return val if val else None
    return None




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
    """Core invite logic — sends one email PER TOUCHPOINT."""
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
        IDRTechnical.tech_status.notin_(
            ["Completed", "Document Review", "Pending Document"]
        )
    ).order_by(IDRTechnical.start_date.asc()).all()

    print(f"[{datetime.now()}] Query returned {len(results)} touchpoint(s) for tomorrow.")
    for tp, func, tech in results:
        ow = func.owner if func else "NO_FUNC_ROW"
        print(f"  - '{tp.name}' | owner='{ow}' | "
              f"status='{tech.tech_status}' | start={tech.start_date}")

    if not results:
        msg = f"No workshops scheduled for {tomorrow_str} in this project."
        print(f"[{datetime.now()}] {msg}")
        return {"status": "success", "emails_sent": 0,
                "skipped_duplicates": 0, "rescheduled_count": 0,
                "message": msg}

    # 3. Resolve project_name once
    project = db.query(Project).filter(Project.id == project_id).first()
    project_name = project.project_name if project else "Project"

    # 4. Send one email per touchpoint
    emails_sent = 0
    skipped_count = 0
    rescheduled_count = 0
    unmapped_names = set()

    for tp, func, tech in results:
        owner_raw = (getattr(func, "owner", None) or "").strip() if func else ""
        tech_owner_raw = (getattr(func, "technical_owner", None) or "").strip() if func else ""
        mod_owner_raw = (getattr(func, "module_owner_functional", None) or "").strip() if func else ""

        owner_identity = person_lookup.get(owner_raw.lower()) if owner_raw else None
        if not owner_identity:
            if owner_raw:
                unmapped_names.add(owner_raw)
                print(f"[{datetime.now()}] SKIP '{tp.name}': "
                      f"owner '{owner_raw}' not in team_master")
            else:
                print(f"[{datetime.now()}] SKIP '{tp.name}': "
                      f"no owner (missing IDRFunctional?)")
            continue

        # Reschedule detection per touchpoint
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

        print(f"[{datetime.now()}] '{tp.name}': prior={prior_date}, "
              f"current={current_date}, status={tech.tech_status} "
              f"-> {invite_kind}")

        if invite_kind == "duplicate":
            skipped_count += 1
            continue
        if invite_kind == "rescheduled":
            rescheduled_count += 1

        # Build recipient set for this touchpoint
        to_set = {owner_identity["person_email"]}

        tech_identity = person_lookup.get(tech_owner_raw.lower()) if tech_owner_raw else None
        if tech_identity:
            to_set.add(tech_identity["person_email"])

        mod_identity = person_lookup.get(mod_owner_raw.lower()) if mod_owner_raw else None
        if mod_identity:
            to_set.add(mod_identity["person_email"])

        dept_email = owner_identity["dept_email"]
        dept_name = owner_identity["dept_name"]

        to_list = sorted(to_set)
        cc_list = [dept_email] if (dept_email and dept_email not in to_set) else []

        # Display names for the participants block
        owner_display = owner_identity["display_name"]
        crm_names = set()
        if tech_identity:
            crm_names.add(tech_identity["display_name"])
        if mod_identity:
            crm_names.add(mod_identity["display_name"])
        crm_str = ", ".join(sorted(crm_names)) if crm_names else "\u2014"

        time_window = _fmt_time(tech)
        prior_date_str = None
        if invite_kind == "rescheduled" and prior_date:
            prior_date_str = prior_date.strftime("%B %d, %Y")

        item = {
            "name": tp.name,
            "tp_id": tp.id,
            "module": (func.module if func else None) or "-",
            "owner": owner_display,
            "integration": (tech.integration_type or "unassigned").upper(),
            "tech_owner": tech_owner_raw or "-",
            "functional_owner": mod_owner_raw or "-",
            "time_window": time_window,
            "invite_kind": invite_kind,
            "prior_date_str": prior_date_str,
            "workshop_date_iso": current_date.isoformat(),
        }

        success = _send_tp_email(
            db=db,
            project_id=project_id,
            project_name=project_name,
            tp=tp,
            tech=tech,
            item=item,
            dept_name=dept_name,
            owner_display=owner_display,
            crm_str=crm_str,
            to_list=to_list,
            cc_list=cc_list,
            tomorrow=tomorrow,
            tomorrow_str=tomorrow_str,
        )
        if success:
            emails_sent += 1

    for name in unmapped_names:
        print(f"[{datetime.now()}] Owner '{name}' not in team_master.")

    parts = []
    if emails_sent > 0:
        parts.append(f"Invites sent for {emails_sent} touchpoint(s)")
    if rescheduled_count > 0:
        parts.append(f"{rescheduled_count} marked as rescheduled")
    if skipped_count > 0:
        parts.append(f"skipped {skipped_count} already-invited touchpoint(s)")
    message = ". ".join(parts) + "." if parts else "No invites sent."

    return {"status": "success", "emails_sent": emails_sent,
            "skipped_duplicates": skipped_count,
            "rescheduled_count": rescheduled_count,
            "message": message}


def _fmt_time(tech):
    """Format time window string."""
    if not tech.start_date:
        return ""
    s = tech.start_date.strftime("%I:%M %p").lstrip("0")
    if tech.end_date:
        e = tech.end_date.strftime("%I:%M %p").lstrip("0")
        return f"{s} \u2013 {e}"
    return s


def _send_tp_email(db, project_id, project_name, tp, tech, item,
                   dept_name, owner_display, crm_str,
                   to_list, cc_list, tomorrow, tomorrow_str):
    """Send one workshop invite email for a single touchpoint.

    Threading: subject is stable per (project, touchpoint_name) so
    MoM and follow-up nudges can reply onto this thread.
    The Graph message ID is stored in WORKSHOP_INVITE_SENT log so
    MoM send and nudge can use reply_to_sent_message directly.
    """
    if not to_list:
        print(f"[{datetime.now()}] No recipients for '{tp.name}'. Skip.")
        return False

    invite_kind = item["invite_kind"]
    is_resched = invite_kind == "rescheduled"

    # CRITICAL: subject is stable per (project, touchpoint_name).
    # MoM send and nudges use this exact subject to anchor the thread.
    # Do NOT include dates or invite counts in the subject.
    subject = f"{project_name} || \U0001f4c5 Workshop Invite \u2013 {tp.name}"

    # For reschedule: find the prior invite's Graph message ID to reply onto
    original_graph_id = None
    if is_resched:
        last_log = db.query(IDRActionLog).filter(
            IDRActionLog.touchpoint_id == tp.id,
            IDRActionLog.action_type == "WORKSHOP_INVITE_SENT"
        ).order_by(IDRActionLog.created_at.desc()).first()
        if last_log:
            original_graph_id = _parse_graph_msg_id(last_log)

    # Teams meeting
    meeting_start = datetime.combine(tomorrow,
                                      datetime.min.time()).replace(hour=10)
    if tech.start_date:
        meeting_start = tech.start_date
    meeting_end = meeting_start + timedelta(hours=1)
    if tech.end_date:
        meeting_end = tech.end_date

    meeting_subject = f"Workshop \u2013 {tp.name} ({tomorrow_str})"
    teams_result = create_teams_meeting(meeting_subject,
                                         meeting_start, meeting_end)
    join_url = teams_result["join_url"] if teams_result["success"] else None
    if not join_url:
        print(f"[{datetime.now()}] Teams meeting failed for "
              f"'{tp.name}': {teams_result['error']}")

    # Build HTML — single-touchpoint layout
    banner = ""
    if is_resched and item.get("prior_date_str"):
        banner = _build_banner([item])

    participants = _participants_html(dept_name, owner_display, crm_str)
    table = _touchpoint_table([item])
    join_block = _teams_join_block(join_url)
    html = _full_html(tomorrow_str, 1, banner, participants,
                      table, join_block)

    # Send — reschedule replies on prior thread; fresh is a new send
    if is_resched and original_graph_id:
        print(f"[{datetime.now()}] '{tp.name}': rescheduled, "
              f"replying on prior thread.")
        result = reply_to_sent_message(
            original_message_id=original_graph_id,
            html_body=html,
            to_recipients=to_list,
            cc_recipients=cc_list if cc_list else None
        )
    else:
        result = send_graph_email(
            to_recipients=to_list,
            subject=subject,
            html_body=html,
            cc_recipients=cc_list if cc_list else None
        )

    if not result["success"]:
        print(f"[{datetime.now()}] Graph send failed for "
              f"'{tp.name}': {result['error']}")
        return False

    # Capture the Graph message ID for MoM threading.
    # find_sent_message looks up the just-sent email by subject
    # so MoM and nudges can reply_to_sent_message on it.
    graph_msg_id = find_sent_message(subject)

    envelope_count = len(to_list) + len(cc_list)

    # Status update + action log
    tech_rec = db.query(IDRTechnical).filter(
        IDRTechnical.touchpoint_id == tp.id
    ).first()
    if (tech_rec and tech_rec.tech_status not in
            ["Completed", "Document Review", "Pending Document"]):
        tech_rec.tech_status = "Scheduled"

    comment = (
        f"WORKSHOP_DATE={item['workshop_date_iso']};"
        f"KIND={invite_kind};"
        f"RECIPIENTS_COUNT={envelope_count}"
    )
    if graph_msg_id:
        comment += f";GRAPH_MSG_ID={graph_msg_id}"

    db.add(IDRActionLog(
        touchpoint_id=tp.id,
        action_type="WORKSHOP_INVITE_SENT",
        action_by="System (Workshop Mailer)",
        comment=comment
    ))
    db.commit()

    disp = ", ".join(to_list)
    print(f"[{datetime.now()}] Sent invite for '{tp.name}' -> {disp}")
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


def _full_html(tomorrow_str, item_count, banner, participants, table, join_block=""):
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
        f'{join_block}'
        f'{banner}'
        f'{participants}'
        f'{table}'
        '</div></div></body></html>'
    )


def _teams_join_block(join_url):
    """Build the Teams join-link block, or a fallback note."""
    if join_url:
        return (
            '<div style="background-color:#f0f9ff;border:1px solid #bae6fd;'
            'border-radius:8px;padding:18px 20px;margin-bottom:25px;text-align:center;">'
            '<p style="margin:0 0 12px 0;font-size:13px;color:#0369a1;'
            'font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">'
            'Microsoft Teams Meeting</p>'
            f'<a href="{join_url}" '
            'style="display:inline-block;background-color:#4f46e5;color:white;'
            'text-decoration:none;font-size:14px;font-weight:600;'
            'padding:10px 28px;border-radius:6px;">Join Workshop</a>'
            '<p style="margin:12px 0 0 0;font-size:11px;color:#64748b;">'
            'Click to join the Teams workshop session.</p>'
            '</div>'
        )
    return (
        '<div style="background-color:#fef3c7;border:1px solid #fde68a;'
        'border-radius:8px;padding:14px 20px;margin-bottom:25px;">'
        '<p style="margin:0;font-size:13px;color:#92400e;">'
        'Teams meeting link could not be generated. The workshop '
        'coordinator will share the join link separately.</p>'
        '</div>'
    )