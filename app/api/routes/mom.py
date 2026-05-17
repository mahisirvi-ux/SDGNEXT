from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import date

from app.core.database import get_db
from app.models.domain import (
    MomSession, IDRMomEntry, IDRDiscussionEntry,
    IntegrationTouchpoint, IDRFunctional, IDRTechnical, IDRActionLog,
    FollowUpItem
)
from app.services.identity_validator import resolve_team_member, enrich_owner_label
from app.core.ai_agent import generate_touchpoint_mom
from app.core.mom_engine import send_touchpoint_mom

router = APIRouter(tags=["mom"])


def _get_project_id(db: Session, tp_id: int) -> int:
    tp = db.query(IntegrationTouchpoint).filter(IntegrationTouchpoint.id == tp_id).first()
    if not tp:
        raise HTTPException(status_code=404, detail="Touchpoint not found")
    return tp.project_id


def _get_session(db: Session, session_id: int) -> MomSession:
    session = db.query(MomSession).filter(MomSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _check_not_sent(session: MomSession):
    if session.status == "SENT":
        raise HTTPException(status_code=403, detail="Session is SENT and frozen. No modifications allowed.")


# ============================================================
# SESSION LIFECYCLE
# ============================================================

@router.get("/api/touchpoints/{tp_id}/mom/sessions")
def list_sessions(tp_id: int, db: Session = Depends(get_db)):
    _get_project_id(db, tp_id)
    sessions = db.query(MomSession).filter(
        MomSession.touchpoint_id == tp_id
    ).order_by(MomSession.session_date.desc()).all()

    return {
        "sessions": [
            {
                "id": s.id,
                "session_date": s.session_date.isoformat(),
                "status": s.status,
                "sent_at": s.sent_at.strftime("%b %d, %Y %H:%M") if s.sent_at else None,
                "entry_count": db.query(IDRMomEntry).filter(IDRMomEntry.session_id == s.id).count(),
                "discussion_count": db.query(IDRDiscussionEntry).filter(IDRDiscussionEntry.session_id == s.id).count()
            }
            for s in sessions
        ]
    }


@router.get("/api/touchpoints/{tp_id}/mom/sessions/{session_id}")
def get_session_detail(tp_id: int, session_id: int, db: Session = Depends(get_db)):
    project_id = _get_project_id(db, tp_id)
    session = _get_session(db, session_id)

    entries = db.query(IDRMomEntry).filter(IDRMomEntry.session_id == session_id).order_by(IDRMomEntry.created_at.asc()).all()
    cache = {}
    entry_list = [
        {
            "id": e.id, "description": e.description or "", "action_point": e.action_point or "",
            "owner": e.owner or "",
            "owner_display": enrich_owner_label(db, e.owner, project_id=project_id, _cache=cache),
            "expected_date": e.expected_date.isoformat() if e.expected_date else "",
            "created_at": e.created_at.strftime("%b %d, %Y %H:%M") if e.created_at else ""
        }
        for e in entries
    ]

    discussions = db.query(IDRDiscussionEntry).filter(IDRDiscussionEntry.session_id == session_id).order_by(IDRDiscussionEntry.created_at.asc()).all()
    disc_list = [
        {"id": d.id, "content": d.content or "", "created_by": d.created_by or "User", "created_at": d.created_at.strftime("%b %d, %Y %H:%M") if d.created_at else ""}
        for d in discussions
    ]

    return {
        "session": {
            "id": session.id, "session_date": session.session_date.isoformat(),
            "status": session.status, "generated_html": session.generated_html,
            "sent_at": session.sent_at.strftime("%b %d, %Y %H:%M") if session.sent_at else None,
            "sent_to": session.sent_to
        },
        "entries": entry_list,
        "discussions": disc_list
    }


@router.post("/api/touchpoints/{tp_id}/mom/sessions")
def create_session(tp_id: int, db: Session = Depends(get_db)):
    _get_project_id(db, tp_id)
    today = date.today()

    active = db.query(MomSession).filter(
        MomSession.touchpoint_id == tp_id,
        MomSession.status.in_(["DRAFT", "GENERATED"])
    ).first()

    if active:
        if active.session_date == today:
            raise HTTPException(status_code=409, detail=f"A session already exists for today. Session ID: {active.id}")
        else:
            raise HTTPException(status_code=400, detail=f"A {active.status} session from {active.session_date.isoformat()} exists. Send or delete it first. Session ID: {active.id}")

    today_sent = db.query(MomSession).filter(
        MomSession.touchpoint_id == tp_id,
        MomSession.session_date == today,
        MomSession.status == "SENT"
    ).first()
    if today_sent:
        raise HTTPException(status_code=409, detail=f"A SENT session already exists for today. Session ID: {today_sent.id}")

    session = MomSession(touchpoint_id=tp_id, session_date=today, status="DRAFT", created_by="User")
    try:
        db.add(session)
        db.commit()
        db.refresh(session)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Session for today already exists (race condition).")

    return JSONResponse(status_code=201, content={"session": {"id": session.id, "session_date": session.session_date.isoformat(), "status": session.status}})


@router.delete("/api/touchpoints/{tp_id}/mom/sessions/{session_id}")
def delete_session(tp_id: int, session_id: int, db: Session = Depends(get_db)):
    _get_project_id(db, tp_id)
    session = _get_session(db, session_id)
    if session.status == "SENT":
        raise HTTPException(status_code=409, detail="Cannot delete a SENT session (audit-protected).")
    db.delete(session)
    db.commit()
    return {"status": "deleted"}


# ============================================================
# SESSION CONTENT: ENTRIES
# ============================================================

@router.get("/api/mom/sessions/{session_id}/entries")
def get_session_entries(session_id: int, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    project_id = _get_project_id(db, session.touchpoint_id)
    entries = db.query(IDRMomEntry).filter(IDRMomEntry.session_id == session_id).order_by(IDRMomEntry.created_at.asc()).all()
    cache = {}
    return {"entries": [
        {"id": e.id, "description": e.description or "", "action_point": e.action_point or "",
         "owner": e.owner or "", "owner_display": enrich_owner_label(db, e.owner, project_id=project_id, _cache=cache),
         "expected_date": e.expected_date.isoformat() if e.expected_date else "",
         "created_at": e.created_at.strftime("%b %d, %Y %H:%M") if e.created_at else ""}
        for e in entries
    ]}


@router.post("/api/mom/sessions/{session_id}/entries")
async def save_session_entries(session_id: int, request: Request, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    _check_not_sent(session)
    project_id = _get_project_id(db, session.touchpoint_id)
    data = await request.json()
    items = data.get("items", [])

    db.query(IDRMomEntry).filter(IDRMomEntry.session_id == session_id).delete()
    warnings = []
    cache = {}
    saved = []

    for item in items:
        raw_owner = (item.get("owner") or "").strip()
        canonical, warning = resolve_team_member(db, raw_owner, project_id=project_id, _cache=cache)
        if warning:
            warnings.append(warning)
        exp_date = None
        if item.get("expected_date"):
            try:
                exp_date = date.fromisoformat(item["expected_date"])
            except (ValueError, TypeError):
                pass
        entry = IDRMomEntry(
            touchpoint_id=session.touchpoint_id, session_id=session_id,
            description=(item.get("description") or "").strip(),
            action_point=(item.get("action_point") or "").strip(),
            owner=canonical, expected_date=exp_date, created_by="User"
        )
        db.add(entry)
        saved.append(entry)

    db.commit()
    enrich_cache = {}
    result = []
    for e in saved:
        db.refresh(e)
        result.append({
            "id": e.id, "description": e.description or "", "action_point": e.action_point or "",
            "owner": e.owner or "", "owner_display": enrich_owner_label(db, e.owner, project_id=project_id, _cache=enrich_cache),
            "expected_date": e.expected_date.isoformat() if e.expected_date else "",
            "created_at": e.created_at.strftime("%b %d, %Y %H:%M") if e.created_at else ""
        })
    return {"status": "success", "entries": result, "warnings": warnings}


@router.delete("/api/mom/sessions/{session_id}/entries/{entry_id}")
def delete_session_entry(session_id: int, entry_id: int, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    _check_not_sent(session)
    entry = db.query(IDRMomEntry).filter(IDRMomEntry.id == entry_id, IDRMomEntry.session_id == session_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"status": "deleted"}


# ============================================================
# SESSION CONTENT: DISCUSSIONS
# ============================================================

@router.get("/api/mom/sessions/{session_id}/discussions")
def get_session_discussions(session_id: int, db: Session = Depends(get_db)):
    _get_session(db, session_id)
    entries = db.query(IDRDiscussionEntry).filter(IDRDiscussionEntry.session_id == session_id).order_by(IDRDiscussionEntry.created_at.asc()).all()
    return {"entries": [
        {"id": e.id, "content": e.content or "", "created_by": e.created_by or "User", "created_at": e.created_at.strftime("%b %d, %Y %H:%M") if e.created_at else ""}
        for e in entries
    ]}


@router.post("/api/mom/sessions/{session_id}/discussions")
async def save_session_discussions(session_id: int, request: Request, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    _check_not_sent(session)
    data = await request.json()
    items = data.get("items", [])

    db.query(IDRDiscussionEntry).filter(IDRDiscussionEntry.session_id == session_id).delete()
    saved = []
    for item in items:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        entry = IDRDiscussionEntry(touchpoint_id=session.touchpoint_id, session_id=session_id, content=content, created_by="User")
        db.add(entry)
        saved.append(entry)
    db.commit()

    result = []
    for e in saved:
        db.refresh(e)
        result.append({"id": e.id, "content": e.content or "", "created_by": e.created_by or "User", "created_at": e.created_at.strftime("%b %d, %Y %H:%M") if e.created_at else ""})
    return {"status": "success", "entries": result}


@router.delete("/api/mom/sessions/{session_id}/discussions/{entry_id}")
def delete_session_discussion(session_id: int, entry_id: int, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    _check_not_sent(session)
    entry = db.query(IDRDiscussionEntry).filter(IDRDiscussionEntry.id == entry_id, IDRDiscussionEntry.session_id == session_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"status": "deleted"}


# ============================================================
# GENERATE & SEND
# ============================================================

@router.post("/api/mom/sessions/{session_id}/generate")
def generate_session_mom(session_id: int, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    _check_not_sent(session)

    tp = db.query(IntegrationTouchpoint).filter(IntegrationTouchpoint.id == session.touchpoint_id).first()
    func = db.query(IDRFunctional).filter(IDRFunctional.touchpoint_id == session.touchpoint_id).first()
    tech = db.query(IDRTechnical).filter(IDRTechnical.touchpoint_id == session.touchpoint_id).first()

    entries = db.query(IDRMomEntry).filter(IDRMomEntry.session_id == session_id).order_by(IDRMomEntry.created_at.asc()).all()
    action_items = [{"description": e.description or "", "action_point": e.action_point or "", "owner": e.owner or "", "expected_date": e.expected_date.isoformat() if e.expected_date else ""} for e in entries]

    disc_entries = db.query(IDRDiscussionEntry).filter(IDRDiscussionEntry.session_id == session_id).order_by(IDRDiscussionEntry.created_at.asc()).all()
    discussions = [{"content": e.content or "", "created_at": e.created_at.strftime("%b %d, %Y %H:%M") if e.created_at else ""} for e in disc_entries]

    open_pointers = tech.open_pointers if tech and tech.open_pointers else None
    touchpoint_name = tp.name if tp else "Unknown Touchpoint"
    module = func.module if func else "Unknown Module"

    html = generate_touchpoint_mom(touchpoint_name=touchpoint_name, module=module, action_items=action_items, discussions=discussions, open_pointers=open_pointers)

    if html:
        session.generated_html = html
        session.status = "GENERATED"
        db.commit()

    return {"html": html, "status": session.status}


@router.post("/api/mom/sessions/{session_id}/send")
async def send_session_mom_endpoint(session_id: int, request: Request, db: Session = Depends(get_db)):
    from datetime import datetime

    session = _get_session(db, session_id)
    _check_not_sent(session)
    if session.status == "DRAFT":
        raise HTTPException(status_code=400, detail="Cannot send a DRAFT session. Generate the MoM first.")

    data = await request.json()
    html_body = data.get("html", "") or session.generated_html or ""
    recipients = data.get("recipients", None)
    if not html_body:
        raise HTTPException(status_code=400, detail="No HTML body available.")

    # SMTP send — irreversible, happens OUTSIDE the DB transaction
    result = send_touchpoint_mom(
        touchpoint_id=session.touchpoint_id,
        html_body=html_body,
        override_recipients=recipients,
        write_action_log=False  # We manage the action log atomically below
    )

    if result.get("success"):
        try:
            # === ATOMIC BLOCK: session flip + follow-ups + action log ===
            session.status = "SENT"
            session.sent_at = datetime.now()
            session.sent_to = result.get("sent_to", [])
            session.generated_html = html_body

            # Spawn follow-ups from MoM entries (idempotent)
            entries = db.query(IDRMomEntry).filter(IDRMomEntry.session_id == session_id).all()
            followups_spawned = 0
            for entry in entries:
                existing = db.query(FollowUpItem).filter(
                    FollowUpItem.source_mom_entry_id == entry.id
                ).first()
                if existing:
                    continue
                fu = FollowUpItem(
                    touchpoint_id=session.touchpoint_id,
                    source_mom_entry_id=entry.id,
                    source_session_id=session.id,
                    description=entry.description or "",
                    action=entry.action_point or "",
                    owner=entry.owner,
                    due_date=entry.expected_date,
                    status="OPEN",
                    created_by="User"
                )
                db.add(fu)
                followups_spawned += 1

            # Action log (append-only)
            recipient_count = len(result.get("sent_to", []))
            log_comment = (
                f"MoM session #{session.id} ({session.session_date}) "
                f"emailed to {recipient_count} recipients; "
                f"{followups_spawned} follow-ups spawned"
            )
            db.add(IDRActionLog(
                touchpoint_id=session.touchpoint_id,
                action_type="MOM_SENT",
                action_by="User",
                comment=log_comment
            ))

            db.commit()  # All-or-nothing
            result["followups_spawned"] = followups_spawned
            # === END ATOMIC BLOCK ===

        except Exception as db_err:
            db.rollback()
            print(f"[CRITICAL] MoM email sent but DB commit failed: {db_err}")
            raise HTTPException(
                status_code=500,
                detail=(
                    "Email was sent successfully, but saving session state failed. "
                    "Please retry — the operation is idempotent."
                )
            )

    return result


# ============================================================
# DEPRECATED (410 Gone)
# ============================================================

_GONE_MSG = "This endpoint is deprecated. Use session-scoped endpoints: GET /api/touchpoints/{tp_id}/mom/sessions"


@router.get("/api/touchpoints/{tp_id}/mom-entries")
def dep1(tp_id: int):
    return JSONResponse(status_code=410, content={"detail": _GONE_MSG})

@router.post("/api/touchpoints/{tp_id}/mom-entries")
async def dep2(tp_id: int, request: Request):
    return JSONResponse(status_code=410, content={"detail": _GONE_MSG})

@router.delete("/api/touchpoints/{tp_id}/mom-entries/{entry_id}")
def dep3(tp_id: int, entry_id: int):
    return JSONResponse(status_code=410, content={"detail": _GONE_MSG})

@router.get("/api/touchpoints/{tp_id}/discussions")
def dep4(tp_id: int):
    return JSONResponse(status_code=410, content={"detail": _GONE_MSG})

@router.post("/api/touchpoints/{tp_id}/discussions")
async def dep5(tp_id: int, request: Request):
    return JSONResponse(status_code=410, content={"detail": _GONE_MSG})

@router.delete("/api/touchpoints/{tp_id}/discussions/{entry_id}")
def dep6(tp_id: int, entry_id: int):
    return JSONResponse(status_code=410, content={"detail": _GONE_MSG})
