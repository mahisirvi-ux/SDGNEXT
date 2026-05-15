import smtplib
import re
import csv
from io import StringIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from app.core.ai_agent import generate_stakeholder_intro
from app.core.database import SessionLocal
from app.models.domain import IDRFunctional, IntegrationTouchpoint, TeamMaster, IDRActionLog
from datetime import datetime

# --- CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
SMTP_USERNAME = "mahi.sirvi@gmail.com"
SMTP_PASSWORD = "klrynpcgevlubkfj" 
RECIPIENTS = ["mahi.sirvi@gmail.com", "gautampatidar15501@gmail.com"]

def generate_and_send_daily_summary():
    """Queries the database and sends the daily executive summary."""
    db = SessionLocal()
    try:
        total = db.query(IDRFunctional).count()
        signed_off = db.query(IDRFunctional).filter(IDRFunctional.idr_status.ilike("%Signed-Off%")).count()
        pending = db.query(IDRFunctional).filter(IDRFunctional.idr_status.ilike("%Pending%")).count()
        in_progress = total - signed_off - pending

        today_str = datetime.now().strftime("%B %d, %Y")

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #1a233a; background-color: #f4f7f9; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <div style="background-color: #1a233a; padding: 20px; text-align: center;">
                        <h2 style="color: white; margin: 0;">SDG<span style="color: #ec4899;">NEXT</span></h2>
                        <p style="color: #94a3b8; font-size: 12px; margin-top: 5px; text-transform: uppercase;">Daily Command Center Report</p>
                    </div>
                    <div style="padding: 30px;">
                        <h3 style="margin-top: 0; color: #334155;">Project Phase 1: Functional Discovery</h3>
                        <p style="color: #64748b; font-size: 14px;">Here is the end-of-day health check for all integration touchpoints as of <strong>{today_str}</strong>.</p>
                        
                        <table style="width: 100%; border-collapse: separate; border-spacing: 10px 0; margin-top: 20px;">
                            <tr>
                                <td style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 15px; text-align: center; width: 25%;">
                                    <p style="font-size: 10px; color: #94a3b8; text-transform: uppercase; margin: 0 0 5px 0; font-weight: bold;">Total</p>
                                    <h2 style="margin: 0; color: #1a233a; font-size: 24px;">{total}</h2>
                                </td>
                                <td style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 15px; text-align: center; width: 25%;">
                                    <p style="font-size: 10px; color: #3b82f6; text-transform: uppercase; margin: 0 0 5px 0; font-weight: bold;">In Progress</p>
                                    <h2 style="margin: 0; color: #1a233a; font-size: 24px;">{in_progress}</h2>
                                </td>
                                <td style="background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 15px; text-align: center; width: 25%;">
                                    <p style="font-size: 10px; color: #f59e0b; text-transform: uppercase; margin: 0 0 5px 0; font-weight: bold;">Pending</p>
                                    <h2 style="margin: 0; color: #1a233a; font-size: 24px;">{pending}</h2>
                                </td>
                                <td style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 15px; text-align: center; width: 25%;">
                                    <p style="font-size: 10px; color: #10b981; text-transform: uppercase; margin: 0 0 5px 0; font-weight: bold;">Signed-Off</p>
                                    <h2 style="margin: 0; color: #1a233a; font-size: 24px;">{signed_off}</h2>
                                </td>
                            </tr>
                        </table>
                        <p style="color: #64748b; font-size: 12px; margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 15px;">
                            <em>To view detailed remarks, open pointers, and specific team bottlenecks, please log in to the SDGNext Dashboard.</em>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 SDGNext Daily Summary - {today_str}"
        msg["From"] = SMTP_USERNAME
        msg["To"] = ", ".join(RECIPIENTS)

        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_USERNAME, RECIPIENTS, msg.as_string())
            
        print(f"[{datetime.now()}] Daily Summary Email Sent Successfully!")

    except Exception as e:
        print(f"[{datetime.now()}] Failed to send summary email: {e}")
    finally:
        db.close()


def generate_and_send_follow_ups():
    """Finds pending items, generates AI executive intro, and conditionally attaches a CSV sheet.

    Post-identity-refactor behaviour:
    - pending_with is now an INDIVIDUAL'S NAME (not a team label).
    - We resolve that name -> (person email, department email) via team_master JOIN
      department_master. The person is in To, their dept group in CC.
    - If a name can't be resolved (unmapped legacy data), we fall back to the
      configured RECIPIENTS list so the email isn't lost during the migration
            window.
    """
    db = SessionLocal()
    try:
        # 1. Build a (name_lower, project_id) -> identity lookup.
        # This ensures follow-ups resolve identity within the correct project context.
        from app.models.domain import DepartmentMaster
        identity_rows = db.query(TeamMaster, DepartmentMaster).join(
            DepartmentMaster, TeamMaster.dept_id == DepartmentMaster.dept_id
        ).filter(TeamMaster.is_active == True).all()

        # Keyed by (name_lower, project_id) for project-scoped resolution
        person_lookup = {}
        for m, d in identity_rows:
            key = (m.full_name.strip().lower(), d.project_id)
            person_lookup[key] = {
                "person_email": m.email,
                "dept_email": d.department_email,
                "dept_name": d.department_name,
                "display_name": m.full_name,
                "project_id": d.project_id,
            }

        # 2. Fetch items that are Pending and assigned
        stuck_items = db.query(IDRFunctional, IntegrationTouchpoint).join(
            IntegrationTouchpoint, IDRFunctional.touchpoint_id == IntegrationTouchpoint.id
        ).filter(
            IDRFunctional.idr_status.ilike("%Pending%"),
            IDRFunctional.pending_with.isnot(None),
            IDRFunctional.pending_with != ""
        ).all()

        if not stuck_items:
            print(f"[{datetime.now()}] No pending items found. Skipping follow-ups.")
            return

        # 3. Group items by the person they're pending with + project context
        grouped_tasks = {}
        for func, tp in stuck_items:
            person = (func.pending_with or "").strip()
            if not person:
                continue
            # Use (name, project_id) as key for project-scoped grouping
            project_id = tp.project_id
            key = (person.lower(), project_id)
            if key not in grouped_tasks:
                grouped_tasks[key] = {"display": person, "project_id": project_id, "items": []}

            # Fetch ONLY the open pointers from history
            history_entries = db.query(IDRActionLog).filter(
                IDRActionLog.touchpoint_id == tp.id
            ).order_by(IDRActionLog.created_at.desc()).limit(5).all()

            pointers_html = "<ul style='margin: 0; padding-left: 15px; font-size: 13px; color: #334155; line-height: 1.5;'>"
            pointers_plain = ""
            has_pointers = False

            if history_entries:
                for record in history_entries:
                    date_str = record.created_at.strftime("%b %d") if record.created_at else "Unknown Date"
                    pointer = record.open_pointer_history.strip() if record.open_pointer_history else ""

                    if pointer:
                        pointers_html += f"<li style='margin-bottom: 6px;'><strong>[{date_str}]</strong> {pointer}</li>"
                        pointers_plain += f"[{date_str}] {pointer}\n"
                        has_pointers = True

            pointers_html += "</ul>"

            if not has_pointers:
                fallback = func.open_pointers or 'No specific action items.'
                pointers_html = f"<em style='color: #64748b;'>{fallback}</em>"
                pointers_plain = fallback

            grouped_tasks[key]["items"].append({
                "touchpoint": tp.name or "Unnamed",
                "module": func.module or "-",
                "pointers": pointers_html,
                "pointers_plain": pointers_plain.strip(),
                "ai_summary": pointers_plain,
            })

        # 4. Send the emails with THRESHOLD LOGIC (> 2 items = CSV Attachment)
        for person_key, group in grouped_tasks.items():
            person_display = group["display"]
            items = group["items"]
            project_id = group["project_id"]

            # Resolve to (To, Cc) emails using project-scoped lookup.
            # person_key is now (name_lower, project_id) tuple.
            identity = person_lookup.get(person_key)
            if identity:
                to_email = identity["person_email"]
                cc_email = identity["dept_email"]
                dept_name = identity["dept_name"]
                greet_name = identity["display_name"]
            else:
                # Fallback: an unmapped legacy name. Don't drop the email — send to
                # the global RECIPIENTS list so somebody sees it.
                print(f"[{datetime.now()}] WARNING: pending_with name '{person_display}' "
                      f"not found in team_master for project_id={project_id}. Falling back to global RECIPIENTS.")
                to_email = RECIPIENTS[0] if RECIPIENTS else SMTP_USERNAME
                cc_email = None
                dept_name = "Unassigned"
                greet_name = person_display

            # Generate the Stakeholder Paragraph
            executive_narrative = generate_stakeholder_intro(greet_name, items)

            csv_data = None
            cards_html = ""

            # --- THRESHOLD LOGIC ---
            if len(items) > 2:
                # Build the CSV file in server memory
                csv_file = StringIO()
                writer = csv.writer(csv_file)
                writer.writerow(["Touchpoint Name", "Module", "Action Required (Open Pointers)"])
                
                for item in items:
                    writer.writerow([item['touchpoint'], item['module'], item['pointers_plain']])
                
                csv_data = csv_file.getvalue()
                csv_file.close()

                cards_html = f"""
                <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 16px 20px; border-radius: 6px; margin-top: 20px;">
                    <div style="font-weight: bold; color: #b45309; font-size: 14px; margin-bottom: 6px;">📎 Detailed Action List Attached</div>
                    <div style="color: #92400e; font-size: 14px; line-height: 1.5;">
                        Due to the volume of pending items (<strong>{len(items)} items</strong>), we have condensed the technical action points into the attached spreadsheet. Please review the attached file for detailed open pointers.
                    </div>
                </div>
                """
            else:
                for item in items:
                    cards_html += f"""
                    <div style="border: 1px solid #cbd5e1; border-radius: 6px; margin-bottom: 20px; background-color: #ffffff; overflow: hidden;">
                        <div style="background-color: #f1f5f9; padding: 12px 20px; border-bottom: 1px solid #cbd5e1;">
                            <h3 style="margin: 0; color: #0f172a; font-size: 16px;">
                                {item['touchpoint']} <span style="float: right; color: #64748b; font-size: 13px; font-weight: normal; margin-top: 2px;">Module: {item['module']}</span>
                            </h3>
                        </div>
                        <div style="padding: 20px;">
                            <strong style="color: #ea580c; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px;">Action Required (Open Pointers)</strong>
                            <div style="margin-top: 10px;">{item['pointers']}</div>
                        </div>
                    </div>
                    """

            html_content = f"""
            <html>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 30px 10px; margin: 0;">
                    <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-top: 4px solid #3b82f6;">
                        
                        <div style="padding: 35px 40px;">
                            <h2 style="margin: 0 0 20px 0; color: #0f172a; font-size: 22px;">Integration Review Required</h2>
                            
                            <div style="color: #334155; font-size: 15px; line-height: 1.6; margin-bottom: 30px;">
                                {executive_narrative}
                            </div>
                            
                            {cards_html}
                            
                            <div style="margin-top: 35px; text-align: center;">
                                <a href="http://127.0.0.1:8000" style="background-color: #0f172a; color: white; text-decoration: none; padding: 12px 26px; border-radius: 6px; font-size: 14px; font-weight: 600; display: inline-block;">Open Command Center</a>
                            </div>
                        </div>
                        
                        <div style="background-color: #f1f5f9; padding: 15px; text-align: center; border-top: 1px solid #e2e8f0;">
                            <p style="color: #94a3b8; font-size: 12px; margin: 0;">Automated briefing via <strong>SDGNext Platform</strong>.</p>
                        </div>
                    </div>
                </body>
            </html>
            """

            msg = MIMEMultipart("mixed")
            msg["Subject"] = f"⚠️ Action Required: {len(items)} Items Pending Your Review"
            msg["From"] = SMTP_USERNAME
            msg["To"] = to_email
            if cc_email and cc_email.lower() != (to_email or "").lower():
                msg["Cc"] = cc_email

            msg.attach(MIMEText(html_content, "html"))

            if csv_data:
                safe_name = (person_display or "person").replace(" ", "_").replace("/", "_")
                attachment = MIMEApplication(csv_data.encode('utf-8'))
                attachment.add_header(
                    'Content-Disposition', 'attachment',
                    filename=f"{safe_name}_Pending_Actions.csv"
                )
                msg.attach(attachment)

            # Build the actual delivery list (To + CC; smtplib needs all envelope recipients)
            envelope_recipients = [to_email]
            if cc_email and cc_email.lower() != (to_email or "").lower():
                envelope_recipients.append(cc_email)

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(SMTP_USERNAME, envelope_recipients, msg.as_string())

            print(f"[{datetime.now()}] Follow-up sent to {person_display} "
                  f"({dept_name}) for {len(items)} items.")

    except Exception as e:
        print(f"[{datetime.now()}] Failed to send follow-ups: {e}")
    finally:
        db.close()