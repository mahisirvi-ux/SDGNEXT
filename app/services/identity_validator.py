"""
Identity Validator Service
==========================
Central place for resolving / validating any free-text name that should
refer to a real person in team_master.

DESIGN NOTES
------------
* We do NOT raise hard errors when a name is unknown. Instead we return
  (resolved_value, warning_or_none) tuples. This is by design:
   - Existing CSVs uploaded today contain unmapped names (CBS, Rahul, etc.)
   - Blocking uploads pre-migration would brick a live demo
   - The unmatched values are collected and surfaced via /admin/migration-template
     so you can map them after the fact.

* Matching is case-insensitive on full_name. We trim whitespace.

* If a caller passes an empty/None value we return (None, None) — empty is valid.
"""
from typing import Optional, Tuple, List, Dict
from sqlalchemy.orm import Session
from app.models.domain import TeamMaster, DepartmentMaster


# A simple per-request cache to avoid re-querying the same name dozens of times
# during a CSV upload. Pass the same _cache dict across calls within one request.
def _normalize(name: Optional[str]) -> str:
    return (name or "").strip()


def resolve_team_member(db: Session, name: Optional[str],
                        _cache: Optional[Dict[str, Optional[TeamMaster]]] = None
                        ) -> Tuple[Optional[str], Optional[str]]:
    """
    Look up a free-text name against team_master.

    Returns: (canonical_name_or_original, warning_message_or_None)
      - If name is None or empty -> (None, None)
      - If the name matches exactly (case-insensitive) -> (matched.full_name, None)
      - If no match -> (original_name, "Unknown team member: 'foo'")

    We always return the original input on a miss so the legacy free-text
    column still gets populated. The warning is collected by the caller.
    """
    raw = _normalize(name)
    if not raw:
        return (None, None)

    if _cache is not None and raw.lower() in _cache:
        cached = _cache[raw.lower()]
        if cached is not None:
            return (cached.full_name, None)
        return (raw, f"Unknown team member: '{raw}'")

    member = db.query(TeamMaster).filter(
        TeamMaster.is_active == True,
        TeamMaster.full_name.ilike(raw)
    ).first()

    if _cache is not None:
        _cache[raw.lower()] = member

    if member:
        return (member.full_name, None)
    return (raw, f"Unknown team member: '{raw}'")


def resolve_pending_with(db: Session, name: Optional[str],
                         _cache: Optional[Dict[str, Optional[TeamMaster]]] = None
                         ) -> Tuple[Optional[str], Optional[str]]:
    """Same as resolve_team_member, but conventionally used at the 'Pending With'
    write sites. Kept as a separate function so we can add stricter rules here
    later (e.g. must be active, must not be CRM-side) without touching callers.
    """
    return resolve_team_member(db, name, _cache)


def enrich_owner_label(db: Session, name: Optional[str],
                       _cache: Optional[Dict[str, Optional[TeamMaster]]] = None
                       ) -> str:
    """For read endpoints. Given a free-text owner name, return either:
      - 'Rahul (CBS)'  if name matched and we know the department
      - 'Rahul'        if matched but no dept lookup (defensive)
      - 'Rahul'        if no match (legacy/unmapped) — unchanged
      - '-'            if name is empty
    Never raises. This is the read-side display helper.
    """
    raw = _normalize(name)
    if not raw:
        return "-"

    cache_key = raw.lower()
    if _cache is not None and cache_key in _cache:
        member = _cache[cache_key]
    else:
        member = db.query(TeamMaster).filter(
            TeamMaster.is_active == True,
            TeamMaster.full_name.ilike(raw)
        ).first()
        if _cache is not None:
            _cache[cache_key] = member

    if not member:
        return raw

    # Look up the dept name (cheap; can be cached at the dept layer too)
    dept = db.query(DepartmentMaster).filter(DepartmentMaster.dept_id == member.dept_id).first()
    if dept:
        return f"{raw} ({dept.department_name})"
    return raw


def list_active_members_with_dept(db: Session) -> List[Dict]:
    """Used by the Pending-With dropdown. Returns rich records so the UI can
    show 'Rahul (CBS)' format. Sorted by name for stable UX.
    """
    rows = db.query(TeamMaster, DepartmentMaster).join(
        DepartmentMaster, TeamMaster.dept_id == DepartmentMaster.dept_id
    ).filter(
        TeamMaster.is_active == True,
        DepartmentMaster.is_active == True
    ).order_by(TeamMaster.full_name.asc()).all()

    return [
        {
            "full_name": m.full_name,
            "email": m.email,
            "dept_id": d.dept_id,
            "department_name": d.department_name,
            "is_crm_user": m.is_crm_user,
            # 'display' is what the dropdown shows AND what gets stored as the
            # free-text pending_with / owner value. Storing the bare name is
            # the safest bet for backward compatibility.
            "display": m.full_name,
            "display_with_dept": f"{m.full_name} ({d.department_name})"
        }
        for m, d in rows
    ]


def resolve_member_email_and_cc(db: Session, name: Optional[str]
                                ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """For email send paths. Returns (to_email, cc_email, display_name)
    where to_email is the person's direct mail, cc_email is the department
    distribution list, and display_name is the canonical name for greetings.

    Falls back gracefully if the name isn't matched (returns (None, None, name)).
    """
    raw = _normalize(name)
    if not raw:
        return (None, None, None)

    row = db.query(TeamMaster, DepartmentMaster).join(
        DepartmentMaster, TeamMaster.dept_id == DepartmentMaster.dept_id
    ).filter(
        TeamMaster.full_name.ilike(raw),
        TeamMaster.is_active == True
    ).first()

    if not row:
        return (None, None, raw)

    member, dept = row
    return (member.email, dept.department_email, member.full_name)
