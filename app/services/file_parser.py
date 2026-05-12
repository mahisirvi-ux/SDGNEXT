import io
import pandas as pd
from sqlalchemy.orm import Session
from app.models.domain import Project, IntegrationTouchpoint, IDRFunctional
from app.services.identity_validator import resolve_team_member


# CSV header -> IDRFunctional column
PART1_MAPPING = {
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
    'Open Pointers': 'open_pointers',
}

# Columns whose values represent people and should be validated against team_master.
NAME_COLUMNS = (
    'owner',
    'module_owner_functional',
    'technical_owner',
    'pending_with',
)


def process_idr_upload(project_name: str, file_content: bytes, db: Session):
    """Parses the uploaded IDR CSV and inserts touchpoints + functional rows.

    Behaviour change (Phase A of identity model):
    - Free-text owner/pending names are still stored verbatim, BUT
    - Each value is looked up in team_master; unmatched values are accumulated
      and returned as `warnings` so an admin can review and patch them after
      the upload. Upload SUCCEEDS regardless — protects demo workflows.

    Returns: {"tasks_added": int, "warnings": [str]}
    """
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project:
        project = Project(project_name=project_name)
        db.add(project)
        db.commit()
        db.refresh(project)

    df = pd.read_csv(io.BytesIO(file_content))

    # Wipe existing touchpoints (existing behavior on re-upload)
    db.query(IntegrationTouchpoint).filter(IntegrationTouchpoint.project_id == project.id).delete()
    db.commit()

    # Per-upload cache so we don't hit team_master once per row
    name_cache = {}
    warnings_seen = set()  # de-dupe; the same unknown name appears in many rows
    tasks_added = 0

    for _, row in df.iterrows():
        tp_name = row.get('Integration Touch Point')
        if pd.isna(tp_name):
            continue

        touchpoint = IntegrationTouchpoint(project_id=project.id, name=str(tp_name).strip())
        db.add(touchpoint)
        db.flush()

        func_data = {"touchpoint_id": touchpoint.id}
        for csv_header, db_column in PART1_MAPPING.items():
            if csv_header not in df.columns:
                continue
            val = row[csv_header]
            raw = str(val).strip() if pd.notna(val) else None

            # Validate columns that hold people-names
            if db_column in NAME_COLUMNS and raw:
                resolved, warn = resolve_team_member(db, raw, _cache=name_cache)
                func_data[db_column] = resolved  # falls back to raw on miss
                if warn:
                    warnings_seen.add(warn)
            else:
                func_data[db_column] = raw

        db.add(IDRFunctional(**func_data))
        tasks_added += 1

    db.commit()

    return {
        "tasks_added": tasks_added,
        "warnings": sorted(warnings_seen),
    }