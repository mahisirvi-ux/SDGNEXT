import csv
import io
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.file_parser import process_idr_upload
from app.models.domain import TeamMaster
import traceback  # <--- Added this to reveal the hidden error

router = APIRouter()

@router.post("/upload-csv/{project_name}")
async def upload_idr_document(project_name: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        content = await file.read()
        
        # Pass to our service layer to handle the heavy lifting
        tasks_added = process_idr_upload(project_name, content, db)
        
        return {"message": f"Successfully parsed and uploaded {tasks_added} IDR touchpoints."}
    except Exception as e:
        # Force the backend to print exactly what went wrong
        print("\n" + "="*50)
        print("CRITICAL ERROR DURING CSV UPLOAD:")
        traceback.print_exc() 
        print("="*50 + "\n")
        
        raise HTTPException(status_code=500, detail=str(e))
# --- NEW: MASTER LOV TEAM UPLOAD ---
@router.post("/upload-teams")
async def upload_teams_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Accepts a CSV with 'Team Name' and 'Contact Email' to update the Master LOV."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        contents = await file.read()
        decoded_content = contents.decode('utf-8-sig') # -sig handles hidden Excel characters
        reader = csv.DictReader(io.StringIO(decoded_content))
        
        # Validate Headers
        if 'Team Name' not in reader.fieldnames or 'Contact Email' not in reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV must contain exact headers: 'Team Name' and 'Contact Email'")

        added = 0
        updated = 0

        for row in reader:
            team_name = row.get('Team Name', '').strip()
            contact_email = row.get('Contact Email', '').strip()

            if not team_name or not contact_email:
                continue # Skip empty rows

            # Check if team already exists
            existing_team = db.query(TeamMaster).filter(TeamMaster.team_name == team_name).first()
            
            if existing_team:
                if existing_team.contact_email != contact_email:
                    existing_team.contact_email = contact_email
                    updated += 1
            else:
                new_team = TeamMaster(team_name=team_name, contact_email=contact_email, is_active=True)
                db.add(new_team)
                added += 1

        db.commit()
        return {"message": f"Success! Added {added} new teams and updated {updated} existing emails."}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing LOV upload: {str(e)}")