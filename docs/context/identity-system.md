# Identity System — SDGNEXT

> **Read this before touching anything that involves owners, pending-with,
> team members, departments, action log authorship, or email recipients.**
> Bugs in this area are silent and cross-cutting — data looks fine in the UI
> while automation skips or misroutes records.

This document is grounded in the actual code as of the current state of
`app/models/domain.py`, `app/services/identity_validator.py`,
`app/services/file_parser.py`, and the routers under `app/api/routes/`.

---

## 1. Who Uses This System

SDGNEXT is an **internal tool for the BusinessNEXT delivery team only**.

Bank staff and bank-vendor staff are **external contacts** — they never log
in, never see the UI. They interact with the system exclusively via email:
they receive workshop invites, RGT templates, and follow-up reminders, and
they reply with filled Word documents that are ingested by the IMAP inbound
service.

This means there are **two conceptually different identity layers**:

| Layer | Who | Where it Lives | Purpose |
|---|---|---|---|
| **BusinessNEXT users** | The actual app users | _Not yet modeled in DB_ | Author of comments, status changes, manual actions |
| **`team_master`** | Bank + vendor contacts | `team_master` + `department_master` | Email recipients, ownership tracking, "pending with" |

Currently the codebase writes `action_by="User"` as a literal string in
`IDRActionLog` (see `app/main.py` and `app/api/routes/tasks.py`). This is a
placeholder. When auth is added, replace the hardcoded `"User"` with the
authenticated BusinessNEXT user's identifier. **Do not** wire BusinessNEXT
user identity through `team_master` — these are different concepts.

---

## 2. Core Principle — Hybrid Validated Text

Owner-like fields (`owner`, `module_owner_functional`, `technical_owner`,
`pending_with`, etc.) are stored as **free-text `String(100)` columns**, not
foreign keys to `team_master`.

This is **intentional**. From `identity_validator.py`:

> Existing CSVs uploaded today contain unmapped names (CBS, Rahul, etc.).
> Blocking uploads pre-migration would brick a live demo. Unmatched values
> are collected and surfaced via `/admin/migration-template` so admins can
> map them after the fact.

### The Rules

1. **Write path**: every name written to an owner-like column passes through
   `resolve_team_member()` or `resolve_pending_with()`. Unmatched names are
   accepted (free-text wins) but contribute to a warnings list.
2. **Read path**: names are enriched at display time via
   `enrich_owner_label()` (e.g., `"Rahul"` → `"Rahul (CBS)"`).
3. **DB stays raw**: the free-text name is the source of truth. Enrichment
   is presentational — never persisted back.

---

## 3. Project Scoping (CRITICAL)

Every identity entity is scoped to a single project:

- `department_master.project_id` → FK to `projects.id`, NOT NULL
- `team_master.dept_id` → FK to `department_master.dept_id`; project is
  reached **transitively** through department
- **`team_master` has no direct `project_id` column** — always join through
  `department_master`

### Department Primary Key Convention

`department_master.dept_id` is a **string PK** like `"BOM-CBS"`, `"IBL-CBS"`,
`"BOM-DWH"`. The project prefix is part of the key, which means the same
department label (e.g., "CBS") exists as different rows for BOM and IBL.

### Uniqueness Constraints

- `uq_project_dept_name` on `(project_id, department_name)` — department
  names are unique **per project**, not globally
- `uq_email_per_dept` on `(email, dept_id)` — the same person's email can
  legitimately appear in multiple departments (different projects) but not
  twice in the same department

### Hard Rules

1. **Never query `team_master` without filtering by project**, either via
   the validator's `project_id` parameter or by joining
   `department_master.project_id`.
2. **Never copy team members across projects** automatically. Same person
   in two projects → two separate `team_master` rows.
3. CSV uploads for departments / team members must go through the
   project-scoped endpoints (see `app/api/routes/upload.py`).

### Common Bug Pattern

Any function that takes a `name` parameter but no `project_id` is almost
certainly broken. If you see one in code review, treat it as a defect
unless explicitly justified.

---

## 4. The Identity Validator — Public Contract

File: `app/services/identity_validator.py`

This is the **only sanctioned path** for resolving a name string to a
person. Do not write ad-hoc queries against `team_master` elsewhere.

### `resolve_team_member(db, name, project_id=None, _cache=None)`

Returns `(canonical_name_or_original, warning_or_None)`.

- Empty / None input → `(None, None)`
- Match (case-insensitive on `full_name`) → `(matched.full_name, None)`
- No match → `(original_name, "Unknown team member: 'foo'")`
- Never raises

Use at **every write site** for owner-like fields.

### `resolve_pending_with(db, name, project_id=None, _cache=None)`

Currently a thin pass-through to `resolve_team_member`. Kept as a separate
function so stricter rules can be added later (e.g., "must be active",
"must not be CRM-side") without touching callers.

### `enrich_owner_label(db, name, project_id=None, _cache=None) -> str`

The **read-side** display helper.

- Empty → `"-"`
- Match + dept found → `"Rahul (CBS)"`
- Match but no dept → `"Rahul"`
- No match → `"Rahul"` (unchanged — preserves legacy data)

Never raises. Use on every read endpoint that returns owner-like fields.

### `list_active_members_with_dept(db, project_id=None) -> List[Dict]`

Powers dropdowns. Returns rich records:

```python
{
    "full_name": "...",
    "email": "...",
    "dept_id": "BOM-CBS",
    "department_name": "CBS",
    "is_crm_user": False,
    "display": "Rahul",                  # what to STORE
    "display_with_dept": "Rahul (CBS)"   # what to SHOW
}
```

The `display` vs `display_with_dept` split matters: dropdowns must show
the parenthesized version, but only the bare name is persisted.

### `resolve_member_email_and_cc(db, name, project_id=None)`

Returns `(to_email, cc_email, display_name)` where `cc_email` is the
department-level distribution list. Used by `workshop_mailer.py`,
`email_engine.py`, and `email_dispatcher.py`. Falls back to
`(None, None, raw_name)` on miss so the calling code can decide whether
to skip the send.

### Per-Request Caching

All four functions accept an optional `_cache` dict. **Always pass one**
when calling in a loop (CSV ingestion, list endpoints, batch emails).
Without it you'll hit `team_master` once per row, which is slow and noisy
in logs. See `file_parser.py` and `tasks.py` for examples.

---

## 5. Owner-Like Fields — Authoritative Audit List

These are the columns that hold person-name strings and must be wired
through the validator on write, enriched on read.

### `IDRFunctional` (Phase 1)
| Column | Validated on write? | Enriched on read? |
|---|---|---|
| `owner` | ✅ via `NAME_COLUMNS` in `file_parser.py` | ✅ `tasks.py:109` |
| `module_owner_functional` | ✅ | ✅ `tasks.py:110` |
| `technical_owner` | ✅ | ✅ `tasks.py:111` and `main.py:141` |
| `pending_with` | ✅ via `resolve_pending_with` (`tasks.py:157`) | ✅ `tasks.py:112` |
| `business_department` | ❌ free text only | ❌ — this is a department name, not a person |

### `IDRTechnical` (Phase 2)
| Column | Validated on write? | Enriched on read? |
|---|---|---|
| `pending_with` | ❌ **GAP** — not currently validated | ❌ raw string returned in `main.py:400` |
| `source_system` | ❌ this is a system name, not a person | — |

### `IDRMomEntry` (Touchpoint MoM)
| Column | Validated on write? | Enriched on read? |
|---|---|---|
| `owner` | ✅ via `resolve_team_member` in session-scoped `mom.py` router | ✅ via `enrich_owner_label` on GET |

### `FollowUpItem` (Follow-Ups)
| Column | Validated on write? | Enriched on read? |
|---|---|---|
| `owner` | ✅ via `resolve_team_member` in `followups.py` router | ✅ via `enrich_owner_label` on GET |
| `closed_by` | ❌ placeholder "User" (BusinessNEXT user, not team_master) | ❌ |
| `created_by` | ❌ placeholder "User" (BusinessNEXT user, not team_master) | ❌ |

> ⚠️ **Known gap**: `IDRTechnical.pending_with` is written without validator
> and read without enrichment. When working on Phase 2 features, fix this
> by routing through `resolve_pending_with` on write and
> `enrich_owner_label` on read.

### `IDRActionLog`
| Column | Notes |
|---|---|
| `action_by` | **Not** a `team_master` reference. This is the BusinessNEXT user who took the action, or a system actor (see §7). |

### What Goes Through The Validator — Quick Test

If a column holds a **person's name** and is **scoped to one project**,
it must use the validator. If it holds a system name, department name,
status, or system-actor label, it must not.

---

## 6. CSV Upload Flow

Order matters. Per `app/api/routes/upload.py`:

```
1. Create project                 → POST /api/projects
2. Upload departments CSV         → POST /api/upload-departments/{project}
3. Upload team members CSV        → POST /api/upload-team-members/{project}
4. Upload IDR / touchpoints CSV   → POST /api/upload (with project context)
```

### Out-of-Order Behavior

If the IDR CSV is uploaded before departments + team members, every
owner-like cell will generate an "Unknown team member" warning. The rows
**still load** (free-text fallback), but they appear unenriched in the UI
and follow-up emails won't find recipients.

### Remediation

- **Bulk fix**: download CSV from
  `GET /admin/migration-template/{project_name}` (defined in
  `app/api/routes/upload.py:260`), fill in mappings, re-upload departments
  and team members. The next read will auto-enrich.
- **Per-row fix**: edit the cell in the UI; the inline-edit endpoints
  re-run validation.
- **Legacy endpoints**: any deprecated upload endpoints that bypassed
  validation now return `410 Gone` with a pointer to
  `/admin/migration-template` (see `upload.py:60`).

---

## 7. `action_by` Vocabulary

`IDRActionLog.action_by` is a free-text label, not a foreign key. Real
values seen in the codebase today:

| Value | Source | Meaning |
|---|---|---|
| `"User"` | `main.py:255, 264, 289, 296`; `tasks.py:170` | Placeholder for the BusinessNEXT user who acted. Replace with real user identity when auth is added. |
| `"System (Inbox Sync)"` | `inbound_service.py:104` | Generated when the IMAP inbound parser auto-updates a record from a returned Word doc. |

### `action_type` Vocabulary

Equally important — the existing taxonomy of action types:

| Value | Source | Meaning |
|---|---|---|
| `"DISCUSSION"` | `main.py:254, 288` | A free-text discussion / remark added to the touchpoint timeline. |
| `"POINTER"` | `main.py:264, 295` | A new open pointer raised on the touchpoint. |
| `"STATUS_CHANGE"` | `inbound_service.py:103` | Auto-generated when a bank reply lands and a status flips. |
| `"MOM_SENT"` | `mom.py:send_session_mom_endpoint` | Logged atomically when a touchpoint MoM email is dispatched. Comment format: "MoM session #{id} ({date}) emailed to {N} recipients; {K} follow-ups spawned". |
| `"FOLLOWUP_CLOSED"` | `followups.py:close_followup` | Logged when a follow-up item is marked closed. Comment includes followup id and description snippet. |
| `"FOLLOWUP_REOPENED"` | `followups.py:reopen_followup` | Logged when a closed follow-up is reopened. |
| `"Manual Update"` | `tasks.py:169` | Generic manual edit catch-all. |

**Don't invent new action_types informally.** Add to this table and
update all relevant filters when introducing a new one.

---

## 8. Email Automation Dependency

This is **why identity bugs are dangerous**. Email workflows resolve
recipients through `team_master`:

- `app/core/email_engine.py` — daily executive summary, weekday follow-ups
- `app/core/email_dispatcher.py` — RGT invite emails
- `app/workshop_mailer.py` — workshop invites grouped by department

### Failure Modes

| Symptom | Cause |
|---|---|
| Follow-up email not sent for a touchpoint | `pending_with` name doesn't resolve in this project |
| Follow-up nudge skipped for owner | Owner name on `FollowUpItem` can't be resolved in team_master for this project |
| Touchpoint missing from workshop invite group | Owner's department isn't in `department_master` for this project |

**Note:** Follow-up nudge emails use a deterministic HTML template
(`_render_nudge_html` in `email_engine.py`), NOT Bedrock/AI. They are
therefore not affected by AWS Bedrock outages.
| Daily summary shows blank owner column | Read endpoint not using `enrich_owner_label` |

These fail **silently**. The UI looks healthy, but the bank contact never
receives the email. Any new feature that adds an email send path **must**
include a count of skipped/unresolved recipients in its logs.

### Required Logging for Email Paths

When sending in a loop, log:
```
Sent X / Y emails for project={project} workflow={name}; skipped Z due to unresolved names: [...]
```

---

## 9. Project Setup Checklist (Onboarding a New Project)

When the team starts on a new project (e.g., a new bank), follow this
order to avoid silent identity gaps:

1. `POST /api/projects` with the project name
2. Prepare department CSV (one row per dept, with email distribution list)
3. `POST /api/upload-departments/{project_name}`
4. Prepare team members CSV (full_name, email, mobile, department_name)
5. `POST /api/upload-team-members/{project_name}`
6. **Sanity check**: `GET /admin/migration-template/{project_name}` —
   should be empty / minimal
7. Now upload IDR CSV. Warnings on this upload should be near-zero.

If you must upload IDR first (legacy data migration), expect warnings,
plan to fix via `/admin/migration-template`.

---

## 10. Do / Don't Quick Reference

### DO
- Always pass `project_id` to validator functions
- Always pass `_cache` when calling in a loop
- Use `resolve_team_member` / `resolve_pending_with` on every owner-like write
- Use `enrich_owner_label` on every owner-like read
- Use `resolve_member_email_and_cc` on every outbound email
- Use the `display` field (bare name) when persisting from a dropdown
- Use the `display_with_dept` field when rendering dropdowns
- Add new owner-like columns to §5's audit list in the same PR

### DON'T
- Don't add FK constraints from IDR tables to `team_master`
  (breaks free-text fallback for unmapped names)
- Don't silently rewrite a user-supplied name to a "canonical" form on write
  (the validator returns the raw name on miss for a reason)
- Don't query `team_master` without project scoping
- Don't persist enriched display strings back to the DB
- Don't raise exceptions on resolution failure — degrade gracefully
- Don't bypass `resolve_member_email_and_cc` when sending email
- Don't add a new `action_type` or `action_by` value without updating §7

---

## 11. Known Gaps and Open Questions

Tracked here so they aren't forgotten when planning Phase 3 / hardening:

- [ ] `IDRTechnical.pending_with` is not validated on write nor enriched
      on read (see §5). Wire up next time Phase 2 endpoints are touched.
- [ ] `action_by` is hardcoded as `"User"` everywhere. Replace with real
      BusinessNEXT user identity once auth lands.
- [ ] No central "BusinessNEXT users" table exists yet — needed for
      meaningful audit trail.
- [ ] Email send paths don't yet log skipped recipients (see §8). Add
      structured logging.
- [ ] Stale `team_master` entries (people who've left the bank) — no
      soft-delete UX exists; `is_active` flag exists but no admin UI to
      toggle it.
- [ ] MoM sessions with status="SENT" are immutable. No endpoint may
      modify entries, discussions, or status of a SENT session. Enforce
      at the router level via `_check_not_sent()` guard.
- [ ] Alias support (e.g., "Rahul" vs "Rahul K." resolving to same
      person) — not currently supported.
- [ ] When a row in `team_master` is deactivated, existing free-text
      references to that person still display but won't enrich. Document
      whether this is desired (audit trail preservation) or a bug.

---

## 12. File-by-File Touch Map

When you need to change identity behavior, these are the only files
that should be touched:

| File | Role |
|---|---|
| `app/models/domain.py` | Schema: `Project`, `DepartmentMaster`, `TeamMaster`, owner-like columns on `IDRFunctional` / `IDRTechnical`, `IDRActionLog.action_by` |
| `app/services/identity_validator.py` | All resolution and enrichment functions |
| `app/services/file_parser.py` | `NAME_COLUMNS` constant + CSV ingestion validation |
| `app/api/routes/upload.py` | Project-scoped upload endpoints + migration template endpoint |
| `app/api/routes/tasks.py` | Phase 1 read enrichment, inline edit validation |
| `app/api/routes/projects.py` | Project CRUD |
| `app/main.py` | Phase 2 endpoints (where the `IDRTechnical.pending_with` gap lives) |
| `app/core/email_engine.py`, `email_dispatcher.py`, `workshop_mailer.py` | Recipient resolution via `resolve_member_email_and_cc` |
| `app/core/inbound_service.py` | Generates `STATUS_CHANGE` action logs with `action_by="System (Inbox Sync)"` |

Changes outside this list that affect identity are almost certainly
violating an invariant — pause and review.
