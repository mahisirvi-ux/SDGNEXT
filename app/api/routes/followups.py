from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import date, datetime

from app.core.database import get_db
from app.models.domain import (
    FollowUpItem, IntegrationTouchpoint, MomSession, IDRActionLog
)
from app.services.identity_validator import resolve_team_member, enrich_owner_label

router = APIRouter(prefix="/api/touchpoints", tags=["followups"])


def _get_project_id(db: Session, tp_id: int) -> int:
    tp = db.query(IntegrationTouchpoint).filter(IntegrationTouchpoint.id == tp_id).first()
    if not tp:
        raise HTTPException(status_code=404, detail="Touchpoint not found")
    return tp.project_id


def _serialize_item(db: Session, item: FollowUpItem, project_id: int, cache: dict) -> dict:
    today = date.today()
    is_overdue = (item.status == "OPEN" and item.due_date is not None and item.due_date < today)

    # Resolve source session date
    source_session_date = None
    if item.source_session_id:
        sess = db.query(MomSession).filter(MomSession.id == item.source_session_id).first()
        source_session_date = sess.session_date.isoformat() if sess else "(deleted)"

    return {
        "id": item.id,
        "description": item.description or "",
        "action": item.action or "",
        "owner": item.owner or "",
        "owner_display": enrich_owner_label(db, item.owner, project_id=project_id, _cache=cache),
        "due_date": item.due_date.isoformat() if item.due_date else "",
        "status": item.status,
        "is_overdue": is_overdue,
        "closed_at": item.closed_at.strftime("%b %d, %Y %H:%M") if item.closed_at else None,
        "close_note": item.close_note or "",
        "source_mom_entry_id": item.source_mom_entry_id,
        "source_session_date": source_session_date,
        "last_nudged_at": item.last_nudged_at.isoformat() if item.last_nudged_at else None,
        "created_at": item.created_at.strftime("%b %d, %Y %H:%M") if item.created_at else ""
    }


# ============================================================
# CRUD
# ============================================================

@router.get("/{tp_id}/followups")
def get_followups(tp_id: int, status: str = "OPEN", db: Session = Depends(get_db)):
    project_id = _get_project_id(db, tp_id)
    query = db.query(FollowUpItem).filter(FollowUpItem.touchpoint_id == tp_id)

    if status.upper() == "OPEN":
        query = query.filter(FollowUpItem.status == "OPEN")
    elif status.upper() == "CLOSED":
        query = query.filter(FollowUpItem.status == "CLOSED")
    # else ALL — no filter

    items = query.order_by(FollowUpItem.created_at.desc()).all()
    cache = {}
    return {"items": [_serialize_item(db, i, project_id, cache) for i in items]}


@router.post("/{tp_id}/followups")
async def create_followup(tp_id: int, request: Request, db: Session = Depends(get_db)):
    project_id = _get_project_id(db, tp_id)
    data = await request.json()

    description = (data.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="Description is required.")

    raw_owner = (data.get("owner") or "").strip()
    cache = {}
    canonical, warning = resolve_team_member(db, raw_owner, project_id=project_id, _cache=cache)
    warnings = [warning] if warning else []

    exp_date = None
    if data.get("due_date"):
        try:
            exp_date = date.fromisoformat(data["due_date"])
        except (ValueError, TypeError):
            pass

    item = FollowUpItem(
        touchpoint_id=tp_id,
        description=description,
        action=(data.get("action") or "").strip(),
        owner=canonical,
        due_date=exp_date,
        status="OPEN",
        created_by="User"
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    enrich_cache = {}
    return JSONResponse(status_code=201, content={
        "item": _serialize_item(db, item, project_id, enrich_cache),
        "warnings": warnings
    })


@router.put("/{tp_id}/followups/{item_id}")
async def update_followup(tp_id: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    project_id = _get_project_id(db, tp_id)
    item = db.query(FollowUpItem).filter(
        FollowUpItem.id == item_id, FollowUpItem.touchpoint_id == tp_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    if item.status == "CLOSED":
        raise HTTPException(status_code=403, detail="Cannot edit a CLOSED follow-up.")

    data = await request.json()
    warnings = []
    cache = {}

    if "description" in data:
        item.description = (data["description"] or "").strip()
    if "action" in data:
        item.action = (data["action"] or "").strip()
    if "owner" in data:
        raw_owner = (data["owner"] or "").strip()
        canonical, warning = resolve_team_member(db, raw_owner, project_id=project_id, _cache=cache)
        if warning:
            warnings.append(warning)
        item.owner = canonical
    if "due_date" in data:
        if data["due_date"]:
            try:
                item.due_date = date.fromisoformat(data["due_date"])
            except (ValueError, TypeError):
                pass
        else:
            item.due_date = None

    db.commit()
    db.refresh(item)

    enrich_cache = {}
    return {"item": _serialize_item(db, item, project_id, enrich_cache), "warnings": warnings}


@router.post("/{tp_id}/followups/{item_id}/close")
async def close_followup(tp_id: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    _get_project_id(db, tp_id)
    item = db.query(FollowUpItem).filter(
        FollowUpItem.id == item_id, FollowUpItem.touchpoint_id == tp_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    if item.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Already closed.")

    data = await request.json()
    item.status = "CLOSED"
    item.closed_at = datetime.now()
    item.closed_by = "User"
    item.close_note = (data.get("close_note") or "").strip() or None

    snippet = (item.description or "")[:60]
    db.add(IDRActionLog(
        touchpoint_id=tp_id,
        action_type="FOLLOWUP_CLOSED",
        action_by="User",
        comment=f"Follow-up #{item.id} closed: {snippet}"
    ))
    db.commit()
    db.refresh(item)

    cache = {}
    project_id = _get_project_id(db, tp_id)
    return {"item": _serialize_item(db, item, project_id, cache)}


@router.post("/{tp_id}/followups/{item_id}/reopen")
def reopen_followup(tp_id: int, item_id: int, db: Session = Depends(get_db)):
    _get_project_id(db, tp_id)
    item = db.query(FollowUpItem).filter(
        FollowUpItem.id == item_id, FollowUpItem.touchpoint_id == tp_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    if item.status == "OPEN":
        raise HTTPException(status_code=409, detail="Already open.")

    item.status = "OPEN"
    item.closed_at = None
    item.closed_by = None
    item.close_note = None

    db.add(IDRActionLog(
        touchpoint_id=tp_id,
        action_type="FOLLOWUP_REOPENED",
        action_by="User",
        comment=f"Follow-up #{item.id} reopened"
    ))
    db.commit()
    db.refresh(item)

    cache = {}
    project_id = _get_project_id(db, tp_id)
    return {"item": _serialize_item(db, item, project_id, cache)}


@router.delete("/{tp_id}/followups/{item_id}")
def delete_followup(tp_id: int, item_id: int, db: Session = Depends(get_db)):
    _get_project_id(db, tp_id)
    item = db.query(FollowUpItem).filter(
        FollowUpItem.id == item_id, FollowUpItem.touchpoint_id == tp_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    if item.source_mom_entry_id is not None:
        raise HTTPException(status_code=409, detail="Cannot delete a MoM-sourced follow-up (traceability).")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}
