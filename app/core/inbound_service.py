import imaplib
import email
import re
import base64
from datetime import datetime
from app.core.parser_engine import extract_bank_specifications
from app.core.database import SessionLocal
from app.models.domain import IDRTechnical, IDRFunctional, IDRActionLog, TechnicalDocument
from sqlalchemy.orm.attributes import flag_modified


# --- CONFIGURATION ---
IMAP_SERVER = "imap.gmail.com"
IMAP_USERNAME = "mahi.sirvi@gmail.com"
IMAP_PASSWORD = "klrynpcgevlubkfj"


def sync_bank_replies():
    """
    Connects to inbox via IMAP, finds replies with WUD-IDs,
    extracts Word documents, saves them for audit, parses specs,
    updates technical_details, and transitions status to 'Document Review'.
    """
    results = {"processed": [], "errors": []}
    db = SessionLocal()

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(IMAP_USERNAME, IMAP_PASSWORD)
        mail.select('inbox')

        # Only process REPLIES (Re:) containing our tracking ID
        status, messages = mail.search(None, '(UNSEEN SUBJECT "Re:" SUBJECT "WUD-ID")')

        if status != 'OK' or not messages[0]:
            return {"message": "No new replies detected.", "processed": [], "errors": []}

        for num in messages[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])

            subject = msg.get("Subject", "")
            sender = msg.get("From", "")

            # Extract WUD-ID
            match = re.search(r'\[WUD-ID:(\d+)\]', subject)
            if not match:
                continue

            wud_id = int(match.group(1).strip())

            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue

                filename = part.get_filename()
                if filename and filename.endswith('.docx'):
                    file_bytes = part.get_payload(decode=True)

                    try:
                        # 1. Save document for audit trail
                        encoded_file = base64.b64encode(file_bytes).decode('utf-8')
                        doc_record = TechnicalDocument(
                            touchpoint_id=wud_id,
                            filename=filename,
                            file_data=encoded_file,
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

                            # 4. Auto-transition status to 'Document Review'
                            old_status = tech_record.tech_status
                            tech_record.tech_status = "Document Review"

                            # 5. Set pending_with to BusinessNEXT Technical Owner
                            func_record = db.query(IDRFunctional).filter(
                                IDRFunctional.touchpoint_id == wud_id
                            ).first()
                            tech_owner = (func_record.technical_owner if func_record else "") or ""
                            tech_record.pending_with = tech_owner

                            # 6. Log the activity
                            log = IDRActionLog(
                                touchpoint_id=wud_id,
                                action_type="STATUS_CHANGE",
                                action_by="System (Inbox Sync)",
                                comment=f"Status: {old_status} → Document Review. Document received from {sender}. Pending with: {tech_owner}.",
                                open_pointer_history=f"[{datetime.now().strftime('%b %d, %Y')}] Document received from bank. Status → Document Review. Pending with {tech_owner}."
                            )
                            db.add(log)

                            db.commit()
                            results["processed"].append(wud_id)
                            print(f"Successfully mapped and SAVED specs for WUD-ID {wud_id}")

                    except Exception as e:
                        db.rollback()
                        results["errors"].append({"wud_id": wud_id, "error": str(e)})
                        print(f"Error processing WUD-ID {wud_id}: {e}")

            mail.store(num, '+FLAGS', '\\Seen')

        mail.logout()
        return {"message": f"Processed {len(results['processed'])} new specifications.", **results}

    except Exception as e:
        print(f"IMAP Connection Error: {e}")
        return {"message": "IMAP Connection Failed", "error": str(e)}
    finally:
        db.close()