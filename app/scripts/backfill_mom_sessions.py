"""
Backfill script: migrate legacy flat IDRMomEntry / IDRDiscussionEntry rows
into MomSession records.

Run ONCE after deploying session_id (nullable) columns.
Idempotent — safe to run multiple times.

Usage:
    cd D:\SDGNext
    python -m app.scripts.backfill_mom_sessions
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from datetime import date
from sqlalchemy import func as sqla_func
from app.core.database import SessionLocal
from app.models.domain import (
    MomSession, IDRMomEntry, IDRDiscussionEntry,
    IDRActionLog, IntegrationTouchpoint
)


def run_backfill():
    db = SessionLocal()
    try:
        # Find all touchpoints that have legacy (session_id=NULL) entries
        tp_ids_from_entries = db.query(IDRMomEntry.touchpoint_id).filter(
            IDRMomEntry.session_id.is_(None)
        ).distinct().all()

        tp_ids_from_disc = db.query(IDRDiscussionEntry.touchpoint_id).filter(
            IDRDiscussionEntry.session_id.is_(None)
        ).distinct().all()

        all_tp_ids = set(
            [r[0] for r in tp_ids_from_entries] +
            [r[0] for r in tp_ids_from_disc]
        )

        if not all_tp_ids:
            print("No legacy entries found (session_id is NULL). Nothing to backfill.")
            return

        print(f"Found {len(all_tp_ids)} touchpoint(s) with legacy MoM data.")
        sessions_created = 0
        entries_linked = 0
        discussions_linked = 0

        for tp_id in all_tp_ids:
            # Check if a backfill session already exists for this TP
            existing = db.query(MomSession).filter(
                MomSession.touchpoint_id == tp_id
            ).first()
            if existing:
                # Link orphan entries to existing session
                updated_e = db.query(IDRMomEntry).filter(
                    IDRMomEntry.touchpoint_id == tp_id,
                    IDRMomEntry.session_id.is_(None)
                ).update({"session_id": existing.id}, synchronize_session=False)

                updated_d = db.query(IDRDiscussionEntry).filter(
                    IDRDiscussionEntry.touchpoint_id == tp_id,
                    IDRDiscussionEntry.session_id.is_(None)
                ).update({"session_id": existing.id}, synchronize_session=False)

                entries_linked += updated_e
                discussions_linked += updated_d
                continue

            # Determine session_date from earliest entry
            earliest_entry = db.query(sqla_func.min(IDRMomEntry.created_at)).filter(
                IDRMomEntry.touchpoint_id == tp_id
            ).scalar()

            earliest_disc = db.query(sqla_func.min(IDRDiscussionEntry.created_at)).filter(
                IDRDiscussionEntry.touchpoint_id == tp_id
            ).scalar()

            earliest = earliest_entry or earliest_disc
            if earliest_disc and (not earliest_entry or earliest_disc < earliest_entry):
                earliest = earliest_disc

            session_date = earliest.date() if earliest else date.today()

            # Check if MOM_SENT log exists
            mom_sent_log = db.query(IDRActionLog).filter(
                IDRActionLog.touchpoint_id == tp_id,
                IDRActionLog.action_type == "MOM_SENT"
            ).order_by(IDRActionLog.created_at.desc()).first()

            status = "SENT" if mom_sent_log else "DRAFT"
            sent_at = mom_sent_log.created_at if mom_sent_log else None

            session = MomSession(
                touchpoint_id=tp_id,
                session_date=session_date,
                status=status,
                sent_at=sent_at,
                created_by="System (Backfill)"
            )
            db.add(session)
            db.flush()  # get session.id

            # Link entries
            updated_e = db.query(IDRMomEntry).filter(
                IDRMomEntry.touchpoint_id == tp_id,
                IDRMomEntry.session_id.is_(None)
            ).update({"session_id": session.id}, synchronize_session=False)

            updated_d = db.query(IDRDiscussionEntry).filter(
                IDRDiscussionEntry.touchpoint_id == tp_id,
                IDRDiscussionEntry.session_id.is_(None)
            ).update({"session_id": session.id}, synchronize_session=False)

            sessions_created += 1
            entries_linked += updated_e
            discussions_linked += updated_d

        db.commit()
        print(f"Backfill complete:")
        print(f"  Sessions created: {sessions_created}")
        print(f"  Entries linked:   {entries_linked}")
        print(f"  Discussions linked: {discussions_linked}")

    except Exception as e:
        db.rollback()
        print(f"Backfill FAILED: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_backfill()
