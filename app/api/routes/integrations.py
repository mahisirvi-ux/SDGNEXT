from fastapi import APIRouter
from datetime import date, timedelta, datetime
from app.core.inbound_service import sync_bank_replies
from app.core.database import SessionLocal
from app.models.domain import Project, IntegrationTouchpoint, IDRFunctional, IDRTechnical, TeamMaster, DepartmentMaster
from app.rgt_engine import generate_rgt
from app.core.email_dispatcher import send_rgt_invite

router = APIRouter()


@router.post("/api/touchpoints/dispatch-tomorrow-rgts/{project_name}")
def dispatch_tomorrow_rgts(project_name: str):
    """
    Triggered by 'Send RGT Templates' button.
    Finds API touchpoints scheduled for TOMORROW within the given project.
    For each: generates RGT, resolves recipients from team_master, sends email.
    
    TO: Owner + Technical Owner + Module Owner
    CC: Owner's department email
    """
    db = SessionLocal()
    try:
        # 1. Validate project
        project = db.query(Project).filter(Project.project_name == project_name).first()
        if not project:
            return {"message": f"Project '{project_name}' not found.", "summary": {"successful": [], "skipped": [], "failed": []}}

        # 2. Build identity lookup (scoped to project)
        identity_rows = db.query(TeamMaster, DepartmentMaster).join(
            DepartmentMaster, TeamMaster.dept_id == DepartmentMaster.dept_id
        ).filter(
            DepartmentMaster.project_id == project.id,
            TeamMaster.is_active == True
        ).all()

        person_lookup = {}
        for m, d in identity_rows:
            person_lookup[m.full_name.strip().lower()] = {
                "email": m.email,
                "dept_email": d.department_email,
            }

        # 3. Query API touchpoints scheduled for TOMORROW
        tomorrow = date.today() + timedelta(days=1)
        tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
        day_after = tomorrow_start + timedelta(days=1)

        results_query = db.query(
            IntegrationTouchpoint, IDRFunctional, IDRTechnical
        ).join(
            IDRFunctional, IntegrationTouchpoint.id == IDRFunctional.touchpoint_id
        ).join(
            IDRTechnical, IntegrationTouchpoint.id == IDRTechnical.touchpoint_id
        ).filter(
            IntegrationTouchpoint.project_id == project.id,
            IDRTechnical.start_date >= tomorrow_start,
            IDRTechnical.start_date < day_after,
            IDRTechnical.integration_type.ilike("%api%")
        ).all()

        if not results_query:
            tomorrow_str = tomorrow.strftime("%d-%m-%Y")
            return {
                "message": f"No API touchpoints scheduled for {tomorrow_str} in project '{project_name}'.",
                "summary": {"successful": [], "skipped": [], "failed": []}
            }

        # 4. Process each touchpoint
        results = {"successful": [], "skipped": [], "failed": []}

        for tp, func, tech in results_query:
            owner_raw = (getattr(func, "owner", None) or "").strip()
            tech_owner_raw = (getattr(func, "technical_owner", None) or "").strip()
            mod_owner_raw = (getattr(func, "module_owner_functional", None) or "").strip()

            # Resolve recipients
            to_emails = []
            cc_emails = []

            # Owner → TO, Department → CC
            owner_info = person_lookup.get(owner_raw.lower()) if owner_raw else None
            if owner_info:
                to_emails.append(owner_info["email"])
                if owner_info["dept_email"]:
                    cc_emails.append(owner_info["dept_email"])

            # Technical Owner → TO
            tech_info = person_lookup.get(tech_owner_raw.lower()) if tech_owner_raw else None
            if tech_info:
                to_emails.append(tech_info["email"])

            # Module Owner → TO
            mod_info = person_lookup.get(mod_owner_raw.lower()) if mod_owner_raw else None
            if mod_info:
                to_emails.append(mod_info["email"])

            # De-duplicate
            to_emails = list(set(to_emails))
            cc_emails = list(set(cc_emails) - set(to_emails))

            if not to_emails:
                results["skipped"].append({
                    "wud_id": tp.id,
                    "name": tp.name,
                    "reason": f"No email found for: {owner_raw}, {tech_owner_raw}, {mod_owner_raw}"
                })
                continue

            # Build RGT data
            tp_data = {
                "id": tp.id,
                "name": tp.name,
                "module": func.module or "",
                "source": getattr(func, "source_system", "") or "",
                "business_flow": getattr(func, "business_flow", "") or "",
                "business_purpose": getattr(func, "business_flow", "") or "",
                "techDetails": tech.technical_details if tech else {}
            }

            try:
                rgt_buffer = generate_rgt(tp_data)
                success = send_rgt_invite(to_emails, cc_emails, tp_data, rgt_buffer)
                if success:
                    results["successful"].append({"wud_id": tp.id, "name": tp.name})
                else:
                    results["failed"].append({"wud_id": tp.id, "name": tp.name, "error": "SMTP failed"})
            except Exception as e:
                results["failed"].append({"wud_id": tp.id, "name": tp.name, "error": str(e)})

        return {"message": "Batch RGT dispatch complete.", "summary": results}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"message": f"Error: {str(e)}", "summary": {"successful": [], "skipped": [], "failed": []}}
    finally:
        db.close()


@router.get("/api/touchpoints/sync-inbox")
def trigger_inbox_sync():
    """Manually triggers the IMAP listener to check for bank replies."""
    result = sync_bank_replies()
    return result