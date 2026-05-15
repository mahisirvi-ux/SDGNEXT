import imaplib
import email
import re
from app.core.parser_engine import extract_bank_specifications
from app.core.database import SessionLocal
from app.models.domain import IDRTechnical
from sqlalchemy.orm.attributes import flag_modified

# --- CONFIGURATION (Matching your setup) ---
IMAP_SERVER = "imap.gmail.com"
IMAP_USERNAME = "mahi.sirvi@gmail.com"
IMAP_PASSWORD = "klrynpcgevlubkfj" # Using your working app password

def sync_bank_replies():
    """
    Connects to the inbox via IMAP, finds replies with WUD-IDs, 
    extracts the Word document, and updates the database.
    """
    results = {"processed": [], "errors": []}
    db = SessionLocal()
    
    try:
        # 1. Connect to Gmail via IMAP
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(IMAP_USERNAME, IMAP_PASSWORD)
        mail.select('inbox')

        # 2. Search for UNREAD emails that contain our Tracking ID format
        status, messages = mail.search(None, '(UNSEEN SUBJECT "Re:" SUBJECT "WUD-ID")')
        
        if status != 'OK' or not messages[0]:
            return {"message": "No new replies detected.", "processed": [], "errors": []}

        # 3. Process each found email
        for num in messages[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])
            
            subject = msg.get("Subject", "")
            
            # Extract the ID using Regex (e.g., "[WUD-ID:5]")
            match = re.search(r'\[WUD-ID:(\d+)\]', subject)
            if not match:
                continue
                
            wud_id = int(match.group(1).strip())
            
            # 4. Find the Word Document attachment
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart': continue
                if part.get('Content-Disposition') is None: continue
                    
                filename = part.get_filename()
                if filename and filename.endswith('.docx'):
                    file_bytes = part.get_payload(decode=True)
                    
                    try:
                        # 5. Extract the data using our Brain module
                        bank_specs = extract_bank_specifications(file_bytes)
                        
                        # 6. Update the Database
                        tech_record = db.query(IDRTechnical).filter(IDRTechnical.touchpoint_id == wud_id).first()
                        if tech_record:
                            # 1. Create a brand new copy of the dictionary (Crucial for SQLAlchemy)
                            current_details = dict(tech_record.technical_details or {})
                            
                            # 2. Add the bank's new answers into it
                            current_details.update(bank_specs)
                            
                            # 3. Assign it back
                            tech_record.technical_details = current_details
                            
                            # 4. FORCE SQLAlchemy to recognize the JSON change and save it
                            flag_modified(tech_record, "technical_details")
                            
                            tech_record.tech_status = "In Progress" 
                            db.commit()
                            
                            results["processed"].append(wud_id)
                            print(f"Successfully mapped and SAVED specs for WUD-ID {wud_id}")
                            
                    except Exception as e:
                        results["errors"].append({"wud_id": wud_id, "error": str(e)})
                        print(f"Error mapping document for WUD-ID {wud_id}: {e}")
            
            # Mark the email as read so we don't process it again
            mail.store(num, '+FLAGS', '\\Seen')

        mail.logout()
        return {"message": f"Processed {len(results['processed'])} new specifications.", **results}

    except Exception as e:
        print(f"IMAP Connection Error: {e}")
        return {"message": "IMAP Connection Failed", "error": str(e)}
    finally:
        db.close()