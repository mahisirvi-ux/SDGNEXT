import re
import base64
import requests
from datetime import datetime, date, timedelta
from app.core.parser_engine import extract_bank_specifications, compare_rgt_fields, validate_rgt_structure
from app.core.email_dispatcher import (
    send_rgt_missing_fields_reply, send_rgt_not_filled_reply, send_rgt_wrong_doc_reply
)
from app.core.database import SessionLocal
from app.models.domain import (
    IDRTechnical, IDRFunctional, IDRActionLog, TechnicalDocument,
    IntegrationTouchpoint, FollowUpItem
)
from app.rgt_engine import generate_rgt
from sqlalchemy.orm.attributes import flag_modified
from app.core.graph_mailer import _get_access_token, _config


def sync_bank_replies():
    """Reads the Outlook inbox via Microsoft Graph, finds unread
    replies containing a WUD-ID, extracts the .docx attachment,
    saves it, parses specs, updates technical_details, and
    transitions status to 'rgt review'.

    Replaces the legacy Gmail IMAP transport. Uses the same Graph
    app registration as outbound mail. Needs Mail.ReadWrite
    (to read messages and mark them as read).
    """
    results = {"processed": [], "errors": []}
    db = SessionLocal()

    try:
        token = _get_access_token()
    except Exception as e:
        db.close()
        print(f"[Inbox Sync] Auth failed: {e}")
        return {"message": "Graph auth failed", "error": str(e)}

    cfg = _config()
    mailbox = cfg["sender_mailbox"]
    base = f"https://graph.microsoft.com/v1.0/users/{mailbox}"
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Fetch unread inbox messages whose subject contains "WUD-ID".
    # Graph $search matches the subject; isRead eq false limits to
    # unprocessed mail. $top caps a single run.
    list_url = (
        f"{base}/mailFolders/Inbox/messages"
        f"?$filter=isRead eq false"
        f"&$select=id,subject,from,hasAttachments"
        f"&$top=50"
    )

    try:
        resp = requests.get(list_url, headers=auth_headers, timeout=45)
    except Exception as e:
        db.close()
        print(f"[Inbox Sync] Message list request error: {e}")
        return {"message": "Graph request failed", "error": str(e)}

    if resp.status_code != 200:
        db.close()
        print(f"[Inbox Sync] Message list failed "
              f"({resp.status_code}): {resp.text[:300]}")
        return {"message": "Graph message list failed",
                "error": resp.text[:300]}

    messages = resp.json().get("value", [])

    for msg in messages:
        subject = msg.get("subject", "") or ""

        # Only process replies carrying our tracking ID
        if "WUD-ID" not in subject:
            continue

        match = re.search(r'\[WUD-ID:(\d+)\]', subject)
        if not match:
            continue
        wud_id = int(match.group(1).strip())

        msg_id = msg.get("id")
        sender = ""
        from_obj = msg.get("from", {})
        if isinstance(from_obj, dict):
            sender = (from_obj.get("emailAddress", {}) or {}).get(
                "address", "")

        if not msg.get("hasAttachments"):
            continue

        # Fetch this message's attachments
        att_url = f"{base}/messages/{msg_id}/attachments"
        try:
            att_resp = requests.get(att_url, headers=auth_headers,
                                    timeout=45)
        except Exception as e:
            results["errors"].append({"wud_id": wud_id,
                                      "error": f"attachment fetch: {e}"})
            continue

        if att_resp.status_code != 200:
            results["errors"].append({
                "wud_id": wud_id,
                "error": f"attachment list {att_resp.status_code}"
            })
            continue

        attachments = att_resp.json().get("value", [])

        for att in attachments:
            filename = att.get("name", "") or ""
            if not filename.endswith(".docx"):
                continue

            content_b64 = att.get("contentBytes")
            if not content_b64:
                continue

            try:
                file_bytes = base64.b64decode(content_b64)

                # 1. Save document for audit trail
                doc_record = TechnicalDocument(
                    touchpoint_id=wud_id,
                    filename=filename,
                    file_data=content_b64,
                    file_type="docx",
                    received_from=sender,
                    notes=f"Auto-captured from email reply: {subject[:100]}"
                )
                db.add(doc_record)

                # 2. Get touchpoint info for RGT regeneration
                tp_record = db.query(IntegrationTouchpoint).filter(
                    IntegrationTouchpoint.id == wud_id
                ).first()
                tp_name = tp_record.name if tp_record else ""

                func_record = db.query(IDRFunctional).filter(
                    IDRFunctional.touchpoint_id == wud_id
                ).first()
                tech_owner = (func_record.technical_owner
                              if func_record else "") or ""

                tech_record = db.query(IDRTechnical).filter(
                    IDRTechnical.touchpoint_id == wud_id
                ).first()

                # Helper: build touchpoint data for RGT regeneration
                def _build_tp_data():
                    return {
                        "id": wud_id,
                        "name": tp_name,
                        "source": getattr(func_record, "source_system", "") or "" if func_record else "",
                        "business_flow": getattr(func_record, "business_flow", "") or "" if func_record else "",
                        "business_purpose": getattr(func_record, "business_flow", "") or "" if func_record else "",
                        "techDetails": tech_record.technical_details if tech_record else {}
                    }

                # ============================================
                # 3. VALIDATE: Is this our RGT document?
                # ============================================
                is_valid_rgt = validate_rgt_structure(file_bytes)

                if not is_valid_rgt:
                    # WRONG DOCUMENT — reply with regenerated RGT
                    print(f"[Inbox Sync] WUD-ID {wud_id}: Wrong document received from {sender}")

                    if tech_record:
                        old_status = tech_record.tech_status
                        tech_record.tech_status = "In Progress"
                        tech_record.pending_with = "Bank Team"

                        log = IDRActionLog(
                            touchpoint_id=wud_id,
                            action_type="RGT_WRONG_DOC",
                            action_by="System (Inbox Sync)",
                            comment=(f"Wrong document received from {sender}. "
                                     f"Status remains In Progress. "
                                     f"Replied with correct RGT template.")
                        )
                        db.add(log)
                        db.commit()

                    # Regenerate RGT and reply
                    try:
                        rgt_buffer = generate_rgt(_build_tp_data())
                        send_rgt_wrong_doc_reply(
                            wud_id=wud_id,
                            api_name=tp_name,
                            bank_email=sender,
                            rgt_buffer=rgt_buffer
                        )
                    except Exception as reply_err:
                        print(f"[Inbox Sync] Wrong doc reply failed WUD-ID {wud_id}: {reply_err}")

                    results["processed"].append(wud_id)
                    continue

                # ============================================
                # 4. PARSE: Extract bank specifications
                # ============================================
                bank_specs = extract_bank_specifications(file_bytes)

                # 5. COMPARE: Run gap analysis
                comparison = compare_rgt_fields(bank_specs)
                missing_fields = comparison["missing"]
                completion_pct = comparison["completion_pct"]
                filled_count = comparison["filled_count"]
                total_fields = comparison["total_fields"]

                # ============================================
                # 6. HANDLE BY COMPLETION LEVEL
                # ============================================

                if completion_pct == 0:
                    # === 0% FILLED: Not filled at all ===
                    print(f"[Inbox Sync] WUD-ID {wud_id}: 0% filled — sending fresh RGT")

                    if tech_record:
                        tech_record.tech_status = "In Progress"
                        tech_record.pending_with = "Bank Team"

                        current_details = dict(tech_record.technical_details or {})
                        current_details["rgt_completion_pct"] = 0
                        current_details["rgt_missing_count"] = total_fields
                        current_details["rgt_last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        tech_record.technical_details = current_details
                        flag_modified(tech_record, "technical_details")

                        log = IDRActionLog(
                            touchpoint_id=wud_id,
                            action_type="RGT_NOT_FILLED",
                            action_by="System (Inbox Sync)",
                            comment=(f"Document received from {sender} but 0% filled. "
                                     f"Status: In Progress. Re-sent RGT template.")
                        )
                        db.add(log)
                        db.commit()

                    # Regenerate RGT and reply
                    try:
                        rgt_buffer = generate_rgt(_build_tp_data())
                        send_rgt_not_filled_reply(
                            wud_id=wud_id,
                            api_name=tp_name,
                            bank_email=sender,
                            rgt_buffer=rgt_buffer
                        )
                    except Exception as reply_err:
                        print(f"[Inbox Sync] Not-filled reply failed WUD-ID {wud_id}: {reply_err}")

                    results["processed"].append(wud_id)

                elif completion_pct == 100:
                    # === 100% FILLED: All done — rgt review ===
                    print(f"[Inbox Sync] WUD-ID {wud_id}: 100% filled — moving to rgt review")

                    if tech_record:
                        current_details = dict(tech_record.technical_details or {})
                        current_details.update(bank_specs)
                        current_details["rgt_completion_pct"] = 100
                        current_details["rgt_missing_count"] = 0
                        current_details["rgt_last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        tech_record.technical_details = current_details
                        flag_modified(tech_record, "technical_details")

                        old_status = tech_record.tech_status
                        tech_record.tech_status = "rgt review"
                        tech_record.pending_with = tech_owner

                        log = IDRActionLog(
                            touchpoint_id=wud_id,
                            action_type="STATUS_CHANGE",
                            action_by="System (Inbox Sync)",
                            comment=(f"Status: {old_status} -> rgt review. "
                                     f"RGT 100% complete. Document from {sender}. "
                                     f"Pending with: {tech_owner}.")
                        )
                        db.add(log)
                        db.commit()

                    results["processed"].append(wud_id)

                else:
                    # === 1-99% FILLED: Partial — In Progress ===
                    print(f"[Inbox Sync] WUD-ID {wud_id}: {completion_pct}% filled — requesting missing fields")

                    if tech_record:
                        current_details = dict(tech_record.technical_details or {})
                        current_details.update(bank_specs)
                        current_details["rgt_completion_pct"] = completion_pct
                        current_details["rgt_missing_count"] = len(missing_fields)
                        current_details["rgt_last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        tech_record.technical_details = current_details
                        flag_modified(tech_record, "technical_details")

                        old_status = tech_record.tech_status
                        tech_record.tech_status = "In Progress"
                        tech_record.pending_with = "Bank Team"

                        log = IDRActionLog(
                            touchpoint_id=wud_id,
                            action_type="STATUS_CHANGE",
                            action_by="System (Inbox Sync)",
                            comment=(f"Status: {old_status} -> In Progress. "
                                     f"RGT {completion_pct}% filled ({filled_count}/{total_fields}). "
                                     f"Document from {sender}. Awaiting missing fields.")
                        )
                        db.add(log)

                        # Create follow-up items for missing fields
                        due_date = date.today() + timedelta(days=3)
                        for mf in missing_fields:
                            followup = FollowUpItem(
                                touchpoint_id=wud_id,
                                description=f"RGT Missing: {mf['label']}",
                                action=f"Bank team to provide '{mf['label']}' in RGT document",
                                owner=tech_owner or "Bank Team",
                                due_date=due_date,
                                status="OPEN",
                                created_by="System (RGT Gap Analysis)"
                            )
                            db.add(followup)

                        # Log gap analysis
                        gap_log = IDRActionLog(
                            touchpoint_id=wud_id,
                            action_type="RGT_GAP_ANALYSIS",
                            action_by="System (Inbox Sync)",
                            comment=(f"RGT Gap Analysis: {filled_count}/{total_fields} "
                                     f"fields filled ({completion_pct}%). "
                                     f"{len(missing_fields)} follow-ups created.")
                        )
                        db.add(gap_log)
                        db.commit()

                    # Reply with missing fields table + bank's own doc attached
                    try:
                        send_rgt_missing_fields_reply(
                            wud_id=wud_id,
                            api_name=tp_name,
                            missing_fields=missing_fields,
                            completion_pct=completion_pct,
                            filled_count=filled_count,
                            total_fields=total_fields,
                            bank_email=sender,
                            bank_doc_bytes=file_bytes
                        )
                    except Exception as reply_err:
                        print(f"[Inbox Sync] Gap reply failed WUD-ID {wud_id}: {reply_err}")

                    results["processed"].append(wud_id)

            except Exception as e:
                db.rollback()
                results["errors"].append({"wud_id": wud_id,
                                          "error": str(e)})
                print(f"[Inbox Sync] Error WUD-ID {wud_id}: {e}")

        # Mark the message as read so it is not reprocessed
        try:
            requests.patch(
                f"{base}/messages/{msg_id}",
                headers={**auth_headers,
                         "Content-Type": "application/json"},
                json={"isRead": True},
                timeout=30
            )
        except Exception as e:
            print(f"[Inbox Sync] Could not mark {msg_id} read: {e}")

    db.close()
    return {
        "message": f"Processed {len(results['processed'])} new specifications.",
        **results
    }
