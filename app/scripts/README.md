# MoM Sessions Migration Scripts

## backfill_mom_sessions.py

Migrates legacy flat `idr_mom_entries` and `idr_discussion_entries` rows
(which have `session_id = NULL`) into proper `MomSession` records.

### When to Run

After deploying the code that adds:
- `mom_sessions` table (via `create_all`)
- `session_id` nullable column on `idr_mom_entries` and `idr_discussion_entries`

### Order

1. **Deploy code** — `create_all` creates the new table and columns (nullable).
2. **Run script**:
   ```
   cd D:\SDGNext
   python -m app.scripts.backfill_mom_sessions
   ```
3. **Verify** — check for zero orphans:
   ```
   python -c "
   from app.core.database import SessionLocal
   from app.models.domain import IDRMomEntry
   db = SessionLocal()
   orphans = db.query(IDRMomEntry).filter(IDRMomEntry.session_id == None).count()
   print(f'Orphan entries: {orphans}')
   db.close()
   "
   ```
4. **Future** — tighten `session_id` to NOT NULL via Alembic migration
   (not done in this PR; document the gap).

### Idempotency

The script is safe to run multiple times. It checks for existing sessions
before creating new ones, and only links entries where `session_id IS NULL`.
