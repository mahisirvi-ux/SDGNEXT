import re
from app.core.database import SessionLocal
from app.models.domain import IntegrationTouchpoint, IDRTechnical, FollowUpItem
from datetime import datetime, date, timedelta
from app.core.graph_mailer import send_graph_email, build_threading_headers, find_sent_message, reply_to_sent_message, find_latest_in_conversation
from app.models.domain import IDRActionLog as _AL
RECIPIENTS = ["mahi.sirvi@gmail.com", "gautampatidar15501@gmail.com"]


def _render_nudge_html(owner_display: str, items: list) -> str:
    """Render follow-up nudge email body from a deterministic template.
    No AI/Bedrock dependency. Items is a list of dicts with keys:
    touchpoint_name, description, action, due_date, urgency."""
    rows = ""
    for item in items:
        urgency = item.get("urgency", "")
        if "Overdue" in urgency:
            color = "#dc2626"
        elif "Due today" in urgency:
            color = "#d97706"
        else:
            color = "#64748b"
        rows += (
            f"<tr>"
            f"<td style='border:1px solid #e2e8f0;padding:8px 10px;'>{item.get('touchpoint_name','')}</td>"
            f"<td style='border:1px solid #e2e8f0;padding:8px 10px;'>{item.get('description','')}</td>"
            f"<td style='border:1px solid #e2e8f0;padding:8px 10px;'>{item.get('action','')}</td>"
            f"<td style='border:1px solid #e2e8f0;padding:8px 10px;'>{item.get('due_date','--')}</td>"
            f"<td style='border:1px solid #e2e8f0;padding:8px 10px;color:{color};font-weight:bold;'>{urgency}</td>"
            f"</tr>"
        )

    return (
        f"<p style='margin:0 0 12px;'>Hi {owner_display},</p>"
        f"<p style='margin:0 0 16px;'>You have <strong>{len(items)}</strong> open follow-up(s) requiring your attention.</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:13px;'>"
        f"<thead><tr style='background:#f1f5f9;'>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Touchpoint</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Description</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Action</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Due</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Urgency</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f"<p style='margin:16px 0 0;'>Please update the status once resolved.</p>"
        f"<p style='margin:4px 0 0;color:#94a3b8;font-size:12px;'>&mdash; SDGNext Automated Nudge</p>"
    )

def generate_and_send_daily_summary():
    """Queries the database and sends the daily executive summary.

    Metrics (post single-stage-workflow):
    - Workshops Scheduled: IDRTechnical rows with tech_status='Scheduled'
    - Workshops Completed: IDRTechnical rows with tech_status='Completed'
    - Open Follow-ups: FollowUpItem rows with status='OPEN'
    - Overdue Follow-ups: Open items where due_date < today
    """
    db = SessionLocal()
    try:
        from sqlalchemy import func as sqla_func

        today = date.today()
        today_str = datetime.now().strftime("%B %d, %Y")

        scheduled = db.query(sqla_func.count(IDRTechnical.id)).filter(
            IDRTechnical.tech_status == "Scheduled"
        ).scalar() or 0

        completed = db.query(sqla_func.count(IDRTechnical.id)).filter(
            IDRTechnical.tech_status == "Completed"
        ).scalar() or 0

        open_fus = db.query(sqla_func.count(FollowUpItem.id)).filter(
            FollowUpItem.status == "OPEN"
        ).scalar() or 0

        overdue_fus = db.query(sqla_func.count(FollowUpItem.id)).filter(
            FollowUpItem.status == "OPEN",
            FollowUpItem.due_date < today,
            FollowUpItem.due_date.isnot(None)
        ).scalar() or 0

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #1a233a; background-color: #f4f7f9; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <div style="background-color: #1a233a; padding: 20px; text-align: center;">
                        <h2 style="color: white; margin: 0;">SDG<span style="color: #ec4899;">NEXT</span></h2>
                        <p style="color: #94a3b8; font-size: 12px; margin-top: 5px; text-transform: uppercase;">Daily Command Center Report</p>
                    </div>
                    <div style="padding: 30px;">
                        <h3 style="margin-top: 0; color: #334155;">Technical Delivery Snapshot</h3>
                        <p style="color: #64748b; font-size: 14px;">Here is the end-of-day delivery status across all integration touchpoints as of <strong>{today_str}</strong>.</p>
                        
                        <table style="width: 100%; border-collapse: separate; border-spacing: 10px 0; margin-top: 20px;">
                            <tr>
                                <td style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 15px; text-align: center; width: 25%;">
                                    <p style="font-size: 10px; color: #0284c7; text-transform: uppercase; margin: 0 0 5px 0; font-weight: bold;">Scheduled</p>
                                    <h2 style="margin: 0; color: #1a233a; font-size: 24px;">{scheduled}</h2>
                                </td>
                                <td style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 15px; text-align: center; width: 25%;">
                                    <p style="font-size: 10px; color: #10b981; text-transform: uppercase; margin: 0 0 5px 0; font-weight: bold;">Completed</p>
                                    <h2 style="margin: 0; color: #1a233a; font-size: 24px;">{completed}</h2>
                                </td>
                                <td style="background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 15px; text-align: center; width: 25%;">
                                    <p style="font-size: 10px; color: #f59e0b; text-transform: uppercase; margin: 0 0 5px 0; font-weight: bold;">Open Follow-ups</p>
                                    <h2 style="margin: 0; color: #1a233a; font-size: 24px;">{open_fus}</h2>
                                </td>
                                <td style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 15px; text-align: center; width: 25%;">
                                    <p style="font-size: 10px; color: #dc2626; text-transform: uppercase; margin: 0 0 5px 0; font-weight: bold;">Overdue</p>
                                    <h2 style="margin: 0; color: #1a233a; font-size: 24px;">{overdue_fus}</h2>
                                </td>
                            </tr>
                        </table>
                        <p style="color: #64748b; font-size: 12px; margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 15px;">
                            <em>To view detailed workshop schedules, follow-ups, and team assignments, please log in to the SDGNext Dashboard.</em>
                        </p>
                    </div>
                </div>
            </body>
                </html>
        """
        subject = f"📊 SDGNext Daily Summary - {today_str}"
        result = send_graph_email(
            to_recipients=RECIPIENTS,
            subject=subject,
            html_body=html_content
        )

        if result["success"]:
            print(f"[{datetime.now()}] Daily Summary Email Sent Successfully!")
        else:
            print(f"[{datetime.now()}] Daily summary send failed: {result['error']}")

    except Exception as e:
        print(f"[{datetime.now()}] Failed to send summary email: {e}")
    finally:
        db.close()




def send_followup_nudges():
    """Sends daily follow-up nudge emails for MANUAL (non-MoM) open items per owner.

    Scope: Only FollowUpItem rows where source_mom_entry_id IS NULL.
    MoM-spawned follow-ups are handled by send_mom_pointer_nudges()
    which groups per-touchpoint and threads onto the original MoM email.

    Behavior:
    - Every day: include ALL open manual follow-ups for each owner.
    - Throttle: once per day via last_nudged_at.
    - Threading: fixed subject per (owner, project).
    - Closed items drop out automatically.
    """
    from app.models.domain import FollowUpItem, DepartmentMaster, Project
    from app.services.identity_validator import resolve_member_email_and_cc
    import hashlib

    db = SessionLocal()
    try:
        today = date.today()
        print(f"[{datetime.now()}] Running follow-up nudge job...")

        # Fetch open MANUAL follow-ups only (source_mom_entry_id IS NULL)
        open_items = db.query(FollowUpItem, IntegrationTouchpoint).join(
            IntegrationTouchpoint, FollowUpItem.touchpoint_id == IntegrationTouchpoint.id
        ).filter(
            FollowUpItem.status == "OPEN",
            FollowUpItem.source_mom_entry_id.is_(None)
        ).all()

        if not open_items:
            print(f"[{datetime.now()}] No open follow-ups. Skipping nudges.")
            return

        # Group by (owner_lower, project_id)
        grouped = {}
        for fu, tp in open_items:
            if not fu.owner or not fu.owner.strip():
                continue
            if fu.last_nudged_at and fu.last_nudged_at >= today:
                continue

            key = (fu.owner.strip().lower(), tp.project_id)
            if key not in grouped:
                grouped[key] = {"owner": fu.owner, "project_id": tp.project_id,
                                "items": [], "fu_objects": []}

            if fu.due_date:
                if fu.due_date == today:
                    urgency = "Due today"
                elif fu.due_date < today:
                    days_over = (today - fu.due_date).days
                    urgency = f"Overdue by {days_over} day(s)"
                else:
                    days_left = (fu.due_date - today).days
                    urgency = f"Due in {days_left} day(s)"
            else:
                urgency = "No due date"

            grouped[key]["items"].append({
                "touchpoint_name": tp.name or "Unknown",
                "description": fu.description or "",
                "action": fu.action or "",
                "due_date": fu.due_date.isoformat() if fu.due_date else "--",
                "urgency": urgency
            })
            grouped[key]["fu_objects"].append(fu)

        if not grouped:
            print(f"[{datetime.now()}] All open items already nudged today. Skipping.")
            return

        sent_count = 0
        skipped = []

        for key, group in grouped.items():
            owner_name = group["owner"]
            project_id = group["project_id"]
            items = group["items"]
            fu_objects = group["fu_objects"]

            to_email, cc_email, display = resolve_member_email_and_cc(
                db, owner_name, project_id=project_id
            )
            if not to_email:
                skipped.append(owner_name)
                continue

            project = db.query(Project).filter(Project.id == project_id).first()
            project_name = project.project_name if project else "Project"

            nudge_body = _render_nudge_html(display or owner_name, items)
            today_str = datetime.now().strftime("%B %d, %Y")
            final_html = (
                "<html><body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;"
                "color:#1e293b;background:#f8fafc;padding:30px;'>"
                "<div style='max-width:700px;margin:0 auto;background:white;border-radius:8px;"
                "box-shadow:0 4px 6px rgba(0,0,0,0.05);overflow:hidden;border-top:4px solid #f59e0b;'>"
                f"<div style='padding:30px;'>"
                f"<h2 style='margin:0 0 10px;color:#0f172a;font-size:18px;'>Action Items Follow-Up</h2>"
                f"<p style='color:#64748b;font-size:13px;margin:0 0 20px;'>{today_str}</p>"
                f"<div style='line-height:1.6;font-size:14px;'>{nudge_body}</div>"
                f"</div>"
                "<div style='padding:15px;text-align:center;background:#f8fafc;"
                "border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;'>"
                "Automated reminder via <strong>SDGNext Command Center</strong></div>"
                "</div></body></html>"
            )

            thread_subject = f"{project_name} || Follow-Up: Open Action Items [{owner_name}]"
            thread_seed = f"sdgnext-followup-{project_id}-{owner_name.lower().strip()}"
            thread_id = f"<{hashlib.md5(thread_seed.encode()).hexdigest()}@sdgnext.local>"

            threading = build_threading_headers(
                in_reply_to=thread_id, references=thread_id
            )
            cc_list = [cc_email] if (cc_email and cc_email.lower() != to_email.lower()) else None

            mail_result = send_graph_email(
                to_recipients=[to_email],
                subject=thread_subject,
                html_body=final_html,
                cc_recipients=cc_list,
                internet_headers=threading
            )

            if mail_result["success"]:
                for fu in fu_objects:
                    fu.last_nudged_at = today
                db.commit()
                sent_count += 1
                print(f"[{datetime.now()}] Nudge sent to {owner_name} ({to_email}) "
                      f"for {len(items)} open item(s).")
            else:
                print(f"[{datetime.now()}] Failed to send nudge to {owner_name}: "
                      f"{mail_result['error']}")

        print(f"[{datetime.now()}] Nudge job complete. Sent: {sent_count}, Skipped: {len(skipped)}")

    except Exception as e:
        print(f"[{datetime.now()}] Follow-up nudge job FAILED: {e}")
    finally:
        db.close()


def _resolve_mom_nudge_recipients(db, touchpoint_id, project_id):
    """Resolve recipients for a touchpoint's MoM-pointer nudge.

    Mirrors the same identity logic as send_touchpoint_mom:
    pending_with, owner, technical_owner from IDRFunctional + IDRTechnical.
    """
    from app.models.domain import IDRFunctional, IDRTechnical
    from app.services.identity_validator import resolve_member_email_and_cc

    func = db.query(IDRFunctional).filter(
        IDRFunctional.touchpoint_id == touchpoint_id
    ).first()
    tech = db.query(IDRTechnical).filter(
        IDRTechnical.touchpoint_id == touchpoint_id
    ).first()

    to_emails = []
    cc_emails = []
    seen_names = set()

    candidates = []
    if func:
        candidates.extend([func.pending_with, func.owner, func.technical_owner])
    if tech:
        candidates.append(getattr(tech, "pending_with", None))

    for name in candidates:
        if not name or not name.strip():
            continue
        name_norm = name.strip().lower()
        if name_norm in seen_names:
            continue
        seen_names.add(name_norm)
        to_email, cc_email, _ = resolve_member_email_and_cc(
            db, name.strip(), project_id=project_id
        )
        if to_email and to_email not in to_emails:
            to_emails.append(to_email)
        if cc_email and cc_email not in cc_emails and cc_email not in to_emails:
            cc_emails.append(cc_email)

    return to_emails, cc_emails


def _render_mom_pointer_html(tp_name, items_display):
    """Render the MoM-pointer nudge email body with urgency coloring."""
    rows = ""
    for item in items_display:
        urgency = item.get("urgency", "")
        if "Overdue" in urgency:
            border_color = "#dc2626"
            text_color = "#dc2626"
        elif "Due today" in urgency:
            border_color = "#d97706"
            text_color = "#d97706"
        else:
            border_color = "#e2e8f0"
            text_color = "#64748b"
        rows += (
            f'<tr style="border-left:3px solid {border_color};">'
            f'<td style="border:1px solid #e2e8f0;padding:8px 10px;">{item.get("description", "")}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:8px 10px;">{item.get("action", "")}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:8px 10px;">{item.get("owner", "")}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:8px 10px;">{item.get("due_date", "--")}</td>'
            f'<td style="border:1px solid #e2e8f0;padding:8px 10px;color:{text_color};font-weight:bold;">{urgency}</td>'
            f'</tr>'
        )

    return (
        f"<p style='margin:0 0 12px;'>Hello Team,</p>"
        f"<p style='margin:0 0 16px;'>Friendly reminder &mdash; the following "
        f"<strong>{len(items_display)}</strong> MoM action item(s) for "
        f"<strong>{tp_name}</strong> are still OPEN. "
        f"Please update on resolution when possible.</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:13px;'>"
        f"<thead><tr style='background:#f1f5f9;'>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Description</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Action</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Owner</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Due</th>"
        f"<th style='border:1px solid #e2e8f0;padding:8px 10px;text-align:left;'>Status</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f"<p style='margin:16px 0 0;'>Reply to this email or update the Workshop Board "
        f"to mark items closed.</p>"
        f"<p style='margin:4px 0 0;color:#94a3b8;font-size:12px;'>&mdash; SDGNext Automated Nudge</p>"
    )


def _send_mom_pointer_email(db, tp, items_display, to_emails, cc_emails, anchor_msg_id):
    """Compose and send the MoM-pointer nudge email as a REPLY on the
    latest message in the touchpoint's thread.

    Strategy:
    1. Find the latest sent message in the touchpoint's workshop
       invite conversation (handles RE: prefix chains correctly)
    2. If found → reply onto it (native Outlook + Gmail threading)
    3. If not found → fallback to fresh send

    Returns True on success.
    """
    from app.models.domain import Project

    tp_name = tp.name or "Touchpoint"

    project_name = "Project"
    if tp.project_id:
        project = db.query(Project).filter(
            Project.id == tp.project_id
        ).first()
        if project:
            project_name = project.project_name

    # Workshop invite subject is the thread root for this touchpoint.
    # find_latest_in_conversation walks from this subject to the
    # most recent reply in that conversation.
    workshop_subject = (
        f"{project_name} || \U0001f4c5 Workshop Invite \u2013 {tp_name}"
    )

    # Subject for fallback fresh send (if no thread found)
    subject = workshop_subject

    html_body = _render_mom_pointer_html(tp_name, items_display)
    today_str = datetime.now().strftime("%B %d, %Y")

    final_html = (
        "<html><body style='font-family:-apple-system,BlinkMacSystemFont,"
        "Segoe UI,Roboto,sans-serif;color:#1e293b;background:#f8fafc;padding:30px;'>"
        "<div style='max-width:700px;margin:0 auto;background:white;border-radius:8px;"
        "box-shadow:0 4px 6px rgba(0,0,0,0.05);overflow:hidden;"
        "border-top:4px solid #4338ca;'>"
        "<div style='padding:30px;'>"
        f"<h2 style='margin:0 0 10px;color:#0f172a;font-size:18px;'>"
        f"MoM Action Items Reminder</h2>"
        f"<p style='color:#64748b;font-size:13px;margin:0 0 20px;'>"
        f"{tp_name} &mdash; {today_str}</p>"
        f"<div style='line-height:1.6;font-size:14px;'>{html_body}</div>"
        "</div>"
        "<div style='padding:15px;text-align:center;background:#f8fafc;"
        "border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;'>"
        "Automated reminder via <strong>SDGNext Command Center</strong>"
        "</div></div></body></html>"
    )

    if not to_emails and not cc_emails:
        return False

    # Find the latest message in this touchpoint's conversation thread
    latest_graph_id = find_latest_in_conversation(workshop_subject)

    if latest_graph_id:
        print(f"[{datetime.now()}] TP {tp.id}: nudge replying on "
              f"latest message in thread.")
        result = reply_to_sent_message(
            original_message_id=latest_graph_id,
            html_body=final_html,
            to_recipients=to_emails,
            cc_recipients=cc_emails if cc_emails else None
        )
    else:
        print(f"[{datetime.now()}] TP {tp.id}: no thread found, "
              f"sending fresh.")
        result = send_graph_email(
            to_recipients=to_emails,
            subject=subject,
            html_body=final_html,
            cc_recipients=cc_emails if cc_emails else None
        )

    if result["success"]:
        print(f"[{datetime.now()}] MoM-pointer nudge sent for "
              f"TP {tp.id} ({tp_name})")
        return True

    print(f"[{datetime.now()}] Failed to send MoM-pointer nudge "
          f"for TP {tp.id}: {result['error']}")
    return False


def _process_touchpoint_mom_nudge(db, touchpoint_id, today, force=False):
    """Process MoM-pointer nudge for a single touchpoint.

    Args:
        db: Active database session (caller manages commit/close).
        touchpoint_id: The touchpoint to process.
        today: date object for throttle comparison.
        force: If True, bypasses the daily last_nudged_at throttle.
            Used by the dev-phase manual trigger button. In production
            cron mode (force=False), respects the once-per-day limit.

    Returns:
        {"sent": bool, "items_count": int, "reason": str}
        reason: "ok", "no_items", "all_throttled", "no_recipients",
                "no_anchor_sent_anyway", "send_failed"
    """
    from app.models.domain import FollowUpItem, IDRActionLog
    from app.core.mom_engine import _parse_mom_msg_id

    tp = db.query(IntegrationTouchpoint).filter(
        IntegrationTouchpoint.id == touchpoint_id
    ).first()
    if not tp:
        return {"sent": False, "items_count": 0, "reason": "no_items"}

    # Fetch open MoM-spawned items for this touchpoint
    open_items = db.query(FollowUpItem).filter(
        FollowUpItem.touchpoint_id == touchpoint_id,
        FollowUpItem.status == "OPEN",
        FollowUpItem.source_mom_entry_id.isnot(None)
    ).all()

    if not open_items:
        return {"sent": False, "items_count": 0, "reason": "no_items"}

    # Apply throttle (skip items already nudged today) unless force=True
    items_to_nudge = []
    items_display = []
    for fu in open_items:
        if not force and fu.last_nudged_at and fu.last_nudged_at >= today:
            continue
        if fu.due_date:
            if fu.due_date == today:
                urgency = "Due today"
            elif fu.due_date < today:
                days_over = (today - fu.due_date).days
                urgency = f"Overdue by {days_over} day(s)"
            else:
                days_left = (fu.due_date - today).days
                urgency = f"Due in {days_left} day(s)"
        else:
            urgency = "No due date"
        items_to_nudge.append(fu)
        items_display.append({
            "description": fu.description or "",
            "action": fu.action or "",
            "owner": fu.owner or "Unassigned",
            "due_date": fu.due_date.isoformat() if fu.due_date else "\u2014",
            "urgency": urgency
        })

    if not items_to_nudge:
        return {"sent": False, "items_count": 0, "reason": "all_throttled"}

    # Resolve recipients
    to_emails, cc_emails = _resolve_mom_nudge_recipients(
        db, touchpoint_id, tp.project_id
    )
    if not to_emails and not cc_emails:
        return {"sent": False, "items_count": len(items_to_nudge),
                "reason": "no_recipients"}

    # Find earliest MOM_SENT log for threading anchor
    earliest_mom = db.query(IDRActionLog).filter(
        IDRActionLog.touchpoint_id == touchpoint_id,
        IDRActionLog.action_type == "MOM_SENT"
    ).order_by(IDRActionLog.created_at.asc()).first()

    anchor_msg_id = None
    if earliest_mom:
        anchor_msg_id = _parse_mom_msg_id(earliest_mom)

    reason = "ok"
    if not anchor_msg_id:
        reason = "no_anchor_sent_anyway"
        print(f"[{datetime.now()}] TP {touchpoint_id} '{tp.name}': "
              f"no MoM anchor. Sending as fresh thread.")

    # Send
    success = _send_mom_pointer_email(
        db, tp, items_display, to_emails, cc_emails, anchor_msg_id
    )
    if not success:
        return {"sent": False, "items_count": len(items_to_nudge),
                "reason": "send_failed"}

    # Post-send: update throttle + action log
    for fu in items_to_nudge:
        fu.last_nudged_at = today
    db.add(IDRActionLog(
        touchpoint_id=touchpoint_id,
        action_type="MOM_NUDGE_SENT",
        action_by="System (MoM Nudge)",
        comment=(
            f"MoM-pointer nudge: {len(items_to_nudge)} open item(s); "
            f"recipients={len(to_emails) + len(cc_emails)}"
        )
    ))

    return {"sent": True, "items_count": len(items_to_nudge), "reason": reason}


def send_mom_pointer_nudges():
    """Daily cron entry point for MoM-spawned follow-up nudges.

    Iterates all touchpoints with open MoM-spawned items and calls
    _process_touchpoint_mom_nudge for each. Commits after each
    successful send.
    """
    from app.models.domain import FollowUpItem

    db = SessionLocal()
    try:
        today = date.today()
        print(f"[{datetime.now()}] Running MoM-pointer nudges...")

        # Get distinct touchpoint_ids with open MoM-spawned items
        tp_ids_rows = db.query(FollowUpItem.touchpoint_id).filter(
            FollowUpItem.status == "OPEN",
            FollowUpItem.source_mom_entry_id.isnot(None)
        ).distinct().all()
        tp_ids = [r[0] for r in tp_ids_rows]

        if not tp_ids:
            print(f"[{datetime.now()}] No open MoM-spawned items.")
            return

        sent_count = 0
        skipped_count = 0

        for tp_id in tp_ids:
            result = _process_touchpoint_mom_nudge(db, tp_id, today, force=False)
            if result["sent"]:
                sent_count += 1
                db.commit()
            else:
                skipped_count += 1

        print(f"[{datetime.now()}] MoM-pointer nudges: sent={sent_count}, "
              f"skipped={skipped_count}")

    except Exception as e:
        print(f"[{datetime.now()}] MoM-pointer nudge job FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
