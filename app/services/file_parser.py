import io
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session
from app.models.domain import Project, IntegrationTouchpoint, IDRFunctional, IDRTechnical
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
    'Owner': 'owner',
    'IDR SignOff Date': 'idr_signoff_date',
    'Pending With': 'pending_with',
    'Open Pointers': 'open_pointers',
}

# CSV header -> IDRTechnical column
# Optional columns. Pre-populate IDRTechnical on upload so the Workshop Board
# is immediately actionable. Missing columns result in NULL values; manual
# fill-in on the UI still works.
PART2_MAPPING = {
    'Integration Type': 'integration_type',
    'Start Time': 'start_date',
    'End Time': 'end_date',
}

# NOTE (Single-Stage Workflow): idr_status defaults to "Signed-Off" at the model
# level (domain.py). If the CSV provides an explicit 'IDR Status' value, it is
# stored as-is. If the CSV column is empty or absent, the model default applies.
# The Workshop Board query no longer filters by idr_status — all uploaded
# touchpoints are immediately visible regardless of status value.

# Columns whose values represent people and should be validated against team_master.
NAME_COLUMNS = (
    'owner',
    'module_owner_functional',
    'technical_owner',
    'pending_with',
)


def _parse_csv_datetime(value):
    """Parse a CSV cell to datetime or None.

    Accepts ISO formats AND dd/mm/yyyy (Indian banking convention).
    Uses dayfirst=True so '07/05/2026' parses as 7-May, not July-5.

    Returns: (datetime|None, warning_string|None)
    """
    if value is None:
        return None, None
    # Handle pandas Timestamp objects (auto-coerced columns)
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None, None
        return value.to_pydatetime(), None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return None, None
    # Try pandas inference with dayfirst=True (Indian convention)
    try:
        parsed = pd.to_datetime(s, dayfirst=True, errors='raise')
        if pd.isna(parsed):
            return None, f"Could not parse date '{s}'"
        return parsed.to_pydatetime(), None
    except Exception:
        pass
    # Fall back to fixed formats
    s2 = s.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(s2, fmt), None
        except ValueError:
            continue
    return None, f"Could not parse date '{s}'"


def process_idr_upload(project_name: str, file_content: bytes, db: Session):
    """Parses the uploaded IDR CSV and inserts touchpoints + functional rows.

    Behaviour:
    - Free-text owner/pending names are still stored verbatim, BUT
    - Each value is looked up in team_master; unmatched values are accumulated
      and returned as `warnings` so an admin can review and patch them after
      the upload. Upload SUCCEEDS regardless — protects demo workflows.
    - IDRTechnical rows are created EAGERLY so the Workshop Board has data
      immediately. Three optional CSV columns pre-populate technical fields.

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

        # --- IDRFunctional (PART1) ---
        func_data = {"touchpoint_id": touchpoint.id}
        for csv_header, db_column in PART1_MAPPING.items():
            if csv_header not in df.columns:
                continue
            val = row[csv_header]
            raw = str(val).strip() if pd.notna(val) else None

            # Validate columns that hold people-names (project-scoped)
            if db_column in NAME_COLUMNS and raw:
                resolved, warn = resolve_team_member(db, raw, project_id=project.id, _cache=name_cache)
                func_data[db_column] = resolved  # falls back to raw on miss
                if warn:
                    warnings_seen.add(warn)
            else:
                func_data[db_column] = raw

        db.add(IDRFunctional(**func_data))

        # --- IDRTechnical (PART2) — Eager creation ---
        # Pre-populate integration_type, start_date, end_date from CSV if present.
        tech_data = {"touchpoint_id": touchpoint.id}
        for csv_header, db_column in PART2_MAPPING.items():
            if csv_header not in df.columns:
                continue
            val = row[csv_header]
            raw = val if pd.notna(val) else None

            if db_column in ('start_date', 'end_date'):
                parsed, warn = _parse_csv_datetime(raw)
                tech_data[db_column] = parsed
                if warn:
                    warnings_seen.add(f"Row '{tp_name}': {warn}")
            else:
                # integration_type — normalize to lowercase canonical set
                if raw is not None:
                    raw_str = str(raw).strip()
                    if raw_str:
                        val_lc = raw_str.lower()
                        if val_lc in ('api', 'database', 'batch'):
                            tech_data[db_column] = val_lc
                        else:
                            tech_data[db_column] = raw_str
                            warnings_seen.add(
                                f"Row '{tp_name}': Unknown Integration Type "
                                f"'{raw_str}'. Expected api / database / batch."
                            )
                    else:
                        tech_data[db_column] = None
                else:
                    tech_data[db_column] = None

        db.add(IDRTechnical(**tech_data))
        tasks_added += 1

    db.commit()

    return {
        "tasks_added": tasks_added,
        "warnings": sorted(warnings_seen),
    }