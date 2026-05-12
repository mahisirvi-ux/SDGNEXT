from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from app.core.inbound_service import sync_bank_replies

# Import our existing Stage 1 & Stage 2 engines
from app.rgt_engine import generate_rgt
from app.core.email_dispatcher import send_rgt_invite

router = APIRouter()

# Define the expected payload structure from your frontend
class TouchpointData(BaseModel):
    id: str
    name: str
    type: str  # e.g., "API", "SFTP", "DB"
    idr_details: str = "Standard IDR"
    # ... any other fields you need

class ScheduledMeeting(BaseModel):
    bank_email: str
    touchpoint_data: dict

class DispatchBatchRequest(BaseModel):
    meetings: List[ScheduledMeeting]


@router.post("/api/touchpoints/dispatch-tomorrow-rgts")
def dispatch_tomorrow_rgts(payload: DispatchBatchRequest):
    """
    Triggered by the new UI Button.
    Filters for API touchpoints and sends individual RGT emails.
    """
    results = {"successful": [], "skipped": [], "failed": []}

    for meeting in payload.meetings:
        bank_email = meeting.bank_email
        tp_data = meeting.touchpoint_data
        wud_id = tp_data.get('id')
        tp_type = tp_data.get('integration', '').upper()  # <--- Changed 'type' to 'integration'
        
        # 1. Filter Check: Only process if it is an API
        if tp_type != "API":
            results["skipped"].append({
                "wud_id": wud_id, 
                "reason": f"Type is {tp_type}, not API"
            })
            continue
            
        try:
            # 2. Generate the RGT Document
            rgt_file_buffer = generate_rgt(tp_data)
            
            # 3. Dispatch the Email
            success = send_rgt_invite(bank_email, tp_data, rgt_file_buffer)
            
            if success:
                # 4. Update Database State
                # db.update_status(wud_id, 'PENDING_BANK_INPUT')
                results["successful"].append({"wud_id": wud_id})
                print(f"RGT Dispatched for WUD-ID {wud_id}")
            else:
                results["failed"].append({"wud_id": wud_id, "error": "SMTP Dispatch Failed"})
                
        except Exception as e:
            results["failed"].append({"wud_id": wud_id, "error": str(e)})
            print(f"Error processing WUD-ID {wud_id}: {str(e)}")

    return {
        "message": "Batch RGT dispatch complete.",
        "summary": results
    }
@router.get("/api/touchpoints/sync-inbox")
def trigger_inbox_sync():
    """
    Manually triggers the IMAP listener to check for bank replies.
    """
    result = sync_bank_replies()
    return result