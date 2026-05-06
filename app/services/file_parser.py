import pandas as pd
import io
from sqlalchemy.orm import Session
from app.models.domain import Project, IntegrationTouchpoint, IDRFunctional

def process_idr_upload(project_name: str, file_content: bytes, db: Session):
    # 1. Ensure the Project exists
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project:
        project = Project(project_name=project_name)
        db.add(project)
        db.commit()
        db.refresh(project)

    # Read the file
    df = pd.read_csv(io.BytesIO(file_content))

    # 2. Clear existing touchpoints for this project to avoid duplicates on re-upload
    db.query(IntegrationTouchpoint).filter(IntegrationTouchpoint.project_id == project.id).delete()
    db.commit()

    # 3. Map Part 1 Excel Columns to IDRFunctional Database Columns
    # Notice we removed 'Integration Touch Point' from here because we extract it separately below!
    part1_mapping = {
        'Module / Journey': 'module',
        'Module Owner (Functional)': 'module_owner_functional',
        'Technical Owner (CRM)': 'technical_owner',
        'Business Flow / Objective': 'business_flow',
        'Integration Direction': 'integration_direction',
        'Source System': 'source_system',
        'Target System': 'target_system',
        'Trigger Mechanism': 'trigger_mechanism',
        'UX Expectation': 'ux_expectation',
        'Business Fallback': 'business_fallback',
        'IDR Remarks / Notes': 'idr_remarks',
        'IDR Status': 'idr_status',
        'Inputs': 'inputs',
        'Expected Output': 'expected_output',
        'Business Department': 'business_department',
        'Owner': 'owner',
        'IDR SignOff Date': 'idr_signoff_date',
        'Pending With': 'pending_with',
        'Open Pointers': 'open_pointers'
    }

    tasks_added = 0
    for _, row in df.iterrows():
        # A. Extract Master Touchpoint Name
        tp_name = row.get('Integration Touch Point')
        if pd.isna(tp_name):
            continue

        # B. Create the Master Touchpoint Record
        touchpoint = IntegrationTouchpoint(project_id=project.id, name=str(tp_name).strip())
        db.add(touchpoint)
        db.flush() # Generates the touchpoint.id without fully committing

        # C. Create the Part 1 Functional Record linked to the Touchpoint
        func_data = {"touchpoint_id": touchpoint.id}
        for csv_header, db_column in part1_mapping.items():
            if csv_header in df.columns:
                val = row[csv_header]
                func_data[db_column] = str(val) if pd.notna(val) else None
        
        idr_func = IDRFunctional(**func_data)
        db.add(idr_func)
        
        tasks_added += 1

    # Commit all rows to the database at once
    db.commit()
    return tasks_added