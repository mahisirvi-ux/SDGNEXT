import csv
import io
import traceback
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.file_parser import process_idr_upload
from app.models.domain import (
    Project, TeamMaster, DepartmentMaster,
    IDRFunctional, IDRTechnical, IntegrationTouchpoint
)

router = APIRouter()


# ============================================================
# IDR DATA UPLOAD (unchanged contract — used by every project)
# ============================================================
@router.post("/upload-csv/{project_name}")
async def upload_idr_document(project_name: str, file: UploadFile = File(...),
                              db: Session = Depends(get_db)):
    try:
        content = await file.read()
        result = process_idr_upload(project_name, content, db)
        # process_idr_upload now returns a dict {tasks_added, warnings}
        if isinstance(result, dict):
            msg = f"Successfully parsed and uploaded {result['tasks_added']} IDR touchpoints."
            if result.get("warnings"):
                msg += f" {len(result['warnings'])} validation warnings (see server log)."
            return {"message": msg, "warnings": result.get("warnings", [])}
        # Legacy shape (just a count)
        return {"message": f"Successfully parsed and uploaded {result} IDR touchpoints."}
    except Exception as e:
        print("\n" + "=" * 50)
        print("CRITICAL ERROR DURING CSV UPLOAD:")
        traceback.print_exc()
        print("=" * 50 + "\n")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# DEPRECATED: /upload-teams (the OLD flat-CSV team uploader)
# ============================================================
# The previous Manage Teams button posted a CSV with columns
# 'Team Name' and 'Contact Email' to this route. With the new identity model
# that endpoint no longer makes sense (we need departments first, then people).
# We keep the route so existing UIs don't 404, but return a clear migration
# message so the user knows what to do.
@router.post("/upload-teams")
async def upload_teams_legacy_deprecated(file: UploadFile = File(...),
                                         db: Session = Depends(get_db)):
    raise HTTPException(
        status_code=410,
        detail=(
            "This endpoint has been deprecated. The team master has been "
            "restructured into two tables: department_master and team_master. "
            "Please use the new uploads: "
            "(1) POST /upload-departments  (2) POST /upload-team-members. "
            "Download the templates from GET /admin/migration-template."
        )
    )


# ============================================================
# NEW: Department upload
# ============================================================
@router.post("/upload-departments/{project_name}")
async def upload_departments_csv(project_name: str, file: UploadFile = File(...),
                                 db: Session = Depends(get_db)):
    """Accepts a CSV with headers:
       'Dept ID', 'Department Name', 'Department Email', 'Is CRM', 'Is Active'
    Departments are created under the specified project.
    'Is CRM' / 'Is Active' accept Yes/No/Y/N/True/False/1/0 (case-insensitive).
    Upserts by Dept ID (the primary key).
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Resolve project
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found. Create the project first.")

    try:
        contents = await file.read()
        decoded = contents.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))

        required = {'Dept ID', 'Department Name', 'Department Email'}
        if not required.issubset(set(reader.fieldnames or [])):
            raise HTTPException(
                status_code=400,
                detail=f"CSV must contain at least these headers: {sorted(required)}. "
                       f"Optional: 'Is CRM', 'Is Active'."
            )

        added, updated, skipped = 0, 0, []
        for row in reader:
            dept_id = (row.get('Dept ID') or '').strip()
            dept_name = (row.get('Department Name') or '').strip()
            dept_email = (row.get('Department Email') or '').strip()

            if not dept_id or not dept_name or not dept_email:
                skipped.append(row)
                continue

            is_crm = _parse_bool(row.get('Is CRM'), default=False)
            is_active = _parse_bool(row.get('Is Active'), default=True)

            existing = db.query(DepartmentMaster).filter(
                DepartmentMaster.dept_id == dept_id
            ).first()

            if existing:
                # Guard: ensure dept_id belongs to THIS project
                if existing.project_id != project.id:
                    skipped.append({**row, "_reason": f"Dept ID '{dept_id}' belongs to another project"})
                    continue
                existing.department_name = dept_name
                existing.department_email = dept_email
                existing.is_crm = is_crm
                existing.is_active = is_active
                updated += 1
            else:
                db.add(DepartmentMaster(
                    dept_id=dept_id,
                    project_id=project.id,
                    department_name=dept_name,
                    department_email=dept_email,
                    is_crm=is_crm,
                    is_active=is_active,
                ))
                added += 1

        db.commit()
        return {
            "message": f"Departments for '{project_name}' — added: {added}, updated: {updated}, skipped: {len(skipped)}.",
            "added": added,
            "updated": updated,
            "skipped_rows": len(skipped),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing departments upload: {str(e)}"
        )


# ============================================================
# NEW: Team Members upload
# ============================================================
@router.post("/upload-team-members/{project_name}")
async def upload_team_members_csv(project_name: str, file: UploadFile = File(...),
                                  db: Session = Depends(get_db)):
    """Accepts a CSV with headers:
       'Full Name', 'Email', 'Mobile Phone', 'Dept ID', 'Is CRM User', 'Is Active'
    Dept ID must already exist under the specified project's departments.
    Upserts by (Email + Dept ID) combination.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Resolve project
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found. Create the project first.")

    try:
        contents = await file.read()
        decoded = contents.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))

        required = {'Full Name', 'Email', 'Dept ID'}
        if not required.issubset(set(reader.fieldnames or [])):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"CSV must contain at least these headers: {sorted(required)}. "
                    f"Optional: 'Mobile Phone', 'Is CRM User', 'Is Active'."
                )
            )

        # Only allow dept_ids that belong to THIS project
        valid_dept_ids = {
            d.dept_id for d in db.query(DepartmentMaster).filter(
                DepartmentMaster.project_id == project.id
            ).all()
        }

        added, updated, skipped_reasons = 0, 0, []
        for row in reader:
            full_name = (row.get('Full Name') or '').strip()
            email = (row.get('Email') or '').strip().lower()
            mobile = (row.get('Mobile Phone') or '').strip() or None
            dept_id = (row.get('Dept ID') or '').strip()

            if not full_name or not email or not dept_id:
                skipped_reasons.append({"row": row, "reason": "Missing required field"})
                continue

            if dept_id not in valid_dept_ids:
                skipped_reasons.append({
                    "row": row,
                    "reason": f"Dept ID '{dept_id}' not found under project '{project_name}' — upload departments first"
                })
                continue

            is_crm_user = _parse_bool(row.get('Is CRM User'), default=False)
            is_active = _parse_bool(row.get('Is Active'), default=True)

            # Upsert by (email + dept_id) — same person in same dept
            existing = db.query(TeamMaster).filter(
                TeamMaster.email == email,
                TeamMaster.dept_id == dept_id
            ).first()

            if existing:
                existing.full_name = full_name
                existing.mobile_phone = mobile
                existing.is_crm_user = is_crm_user
                existing.is_active = is_active
                updated += 1
            else:
                db.add(TeamMaster(
                    full_name=full_name,
                    email=email,
                    mobile_phone=mobile,
                    dept_id=dept_id,
                    is_crm_user=is_crm_user,
                    is_active=is_active,
                ))
                added += 1

        db.commit()
        return {
            "message": f"Team members for '{project_name}' — added: {added}, updated: {updated}, skipped: {len(skipped_reasons)}.",
            "added": added,
            "updated": updated,
            "skipped_rows": skipped_reasons,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing team members upload: {str(e)}"
        )


# ============================================================
# Migration template generator (Project-Scoped)
# ============================================================
@router.get("/admin/migration-template/{project_name}")
def download_migration_template(project_name: str, db: Session = Depends(get_db)):
    """Returns a CSV containing all distinct legacy names found across
       IDRFunctional for the specified project:
       .owner, .module_owner_functional, .technical_owner, .pending_with
       IDRTechnical.pending_with
    Pre-fills 'Suggested Dept ID' = 'UNASSIGNED' so you can run the upload
    immediately for a safe baseline, then refine departmental assignments later.
    """
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found.")

    names = set()

    # Collect from IDRFunctional for THIS project's touchpoints only
    rows = db.query(IDRFunctional).join(
        IntegrationTouchpoint, IDRFunctional.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project.id
    ).all()

    for func in rows:
        for v in (func.owner, func.module_owner_functional, func.technical_owner, func.pending_with):
            if v and str(v).strip() and str(v).strip().lower() not in ("none", "nan"):
                names.add(str(v).strip())

    # Collect from IDRTechnical pending_with for this project's touchpoints
    rows2 = db.query(IDRTechnical.pending_with).join(
        IntegrationTouchpoint, IDRTechnical.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project.id
    ).all()
    for (p,) in rows2:
        if p and str(p).strip() and str(p).strip().lower() not in ("none", "nan"):
            names.add(str(p).strip())

    # Build the CSV
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([
        "Full Name", "Email", "Mobile Phone", "Dept ID",
        "Is CRM User", "Is Active"
    ])
    for n in sorted(names, key=lambda s: s.lower()):
        writer.writerow([n, "", "", "UNASSIGNED", "No", "Yes"])

    stream.seek(0)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={project_name}_identity_migration_template.csv"
        }
    )


# ============================================================
# Helper
# ============================================================
def _parse_bool(val, default=False) -> bool:
    """Tolerant boolean parser for CSV cells.
    Accepts: Yes/No, Y/N, True/False, 1/0, (empty -> default)."""
    if val is None:
        return default
    s = str(val).strip().lower()
    if not s:
        return default
    if s in ("yes", "y", "true", "t", "1"):
        return True
    if s in ("no", "n", "false", "f", "0"):
        return False
    return default
