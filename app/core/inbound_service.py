import re
import base64
import requests
from datetime import datetime
from app.core.parser_engine import extract_bank_specifications
from app.core.database import SessionLocal
from app.models.domain import IDRTechnical, IDRFunctional, IDRActionLog, TechnicalDocument
from sqlalchemy.orm.attributes import flag_modified
from app.core.graph_mailer import _get_access_token, _config


def sync_bank_replies():
    """Reads the Outlook inbox via Microsoft Graph, finds unread
    replies containing a WUD-ID, extracts the .docx attachment,
    saves it, parses specs, updates technical_details, and
    transitions status to 'Document Review'.

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

                # 2. Parse specifications
                bank_specs = extract_bank_specifications(file_bytes)

                # 3. Update technical_details
                tech_record = db.query(IDRTechnical).filter(
                    IDRTechnical.touchpoint_id == wud_id
                ).first()

                if tech_record:
                    current_details = dict(tech_record.technical_details or {})
                    current_details.update(bank_specs)
                    tech_record.technical_details = current_details
                    flag_modified(tech_record, "technical_details")

                    # 4. Auto-transition status
                    old_status = tech_record.tech_status
                    tech_record.tech_status = "Document Review"

                    # 5. Set pending_with to BusinessNEXT Technical Owner
                    func_record = db.query(IDRFunctional).filter(
                        IDRFunctional.touchpoint_id == wud_id
                    ).first()
                    tech_owner = (func_record.technical_owner
                                  if func_record else "") or ""
                    tech_record.pending_with = tech_owner

                    # 6. Log the activity
                    log = IDRActionLog(
                        touchpoint_id=wud_id,
                        action_type="STATUS_CHANGE",
                        action_by="System (Inbox Sync)",
                        comment=(f"Status: {old_status} -> Document "
                                 f"Review. Document received from "
                                 f"{sender}. Pending with: {tech_owner}."),
                        open_pointer_history=(
                            f"[{datetime.now().strftime('%b %d, %Y')}] "
                            f"Document received from bank. Status -> "
                            f"Document Review. Pending with {tech_owner}.")
                    )
                    db.add(log)

                    db.commit()
                    results["processed"].append(wud_id)
                    print(f"[Inbox Sync] Mapped specs for WUD-ID {wud_id}")

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