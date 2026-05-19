from sqlalchemy import Column, Integer, String, Text, Date, DateTime, JSON, Boolean, ForeignKey, TIMESTAMP, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

# ============================================================
# CORE PROJECT MODEL
# ============================================================

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(50), unique=True, index=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)

    touchpoints = relationship("IntegrationTouchpoint", back_populates="project", cascade="all, delete-orphan")
    departments = relationship("DepartmentMaster", back_populates="project", cascade="all, delete-orphan")


class IntegrationTouchpoint(Base):
    __tablename__ = "integration_touchpoints"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    name = Column(String(200), index=True)

    project = relationship("Project", back_populates="touchpoints")
    functional_discovery = relationship("IDRFunctional", back_populates="touchpoint", uselist=False, cascade="all, delete-orphan")
    action_logs = relationship("IDRActionLog", back_populates="touchpoint", cascade="all, delete-orphan", order_by="desc(IDRActionLog.created_at)")


class IDRFunctional(Base):
    __tablename__ = "idr_functional_discovery"
    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="CASCADE"), unique=True)

    module = Column(String(100))
    module_owner_functional = Column(String(100))
    technical_owner = Column(String(100))
    business_flow = Column(Text)
    integration_direction = Column(String(50))
    source_system = Column(String(100))
    target_system = Column(String(100))
    trigger_mechanism = Column(String(100))
    ux_expectation = Column(String(100))
    business_fallback = Column(Text)
    idr_remarks = Column(Text)
    idr_status = Column(String(50), default="Signed-Off")

    inputs = Column(Text)
    expected_output = Column(Text)
    business_department = Column(String(100))
    owner = Column(String(100))
    idr_signoff_date = Column(String(50))
    pending_with = Column(String(100))
    open_pointers = Column(Text)

    touchpoint = relationship("IntegrationTouchpoint", back_populates="functional_discovery")


class IDRActionLog(Base):
    __tablename__ = "idr_action_logs"
    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="CASCADE"))

    action_type = Column(String(50))
    action_by = Column(String(100))

    comment = Column(Text)                     # Strictly for Remarks
    open_pointer_history = Column(Text)        # Strictly for Pointers history
    created_at = Column(TIMESTAMP, server_default=func.now())

    touchpoint = relationship("IntegrationTouchpoint", back_populates="action_logs")


class IDRTechnical(Base):
    """Phase 2: Technical Integration Requirements"""
    __tablename__ = "idr_technical"

    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="CASCADE"))

    tech_status = Column(String, default="Pending Workshop", index=True)
    pending_with = Column(String)

    source_system = Column(String, nullable=True)
    start_date = Column(DateTime, nullable=True)   # Includes time-of-day for workshop scheduling
    end_date = Column(DateTime, nullable=True)

    integration_type = Column(String, nullable=True)  # "API", "Database", "Batch"
    technical_details = Column(JSON, default={})
    open_pointers = Column(Text)


# ============================================================
# IDENTITY MODEL (NEW)
# ============================================================
# Two-table identity model:
#   DepartmentMaster: the *organization* (CBS, Data Warehouse, Website Vendor, CRM-GENERIC, ...)
#   TeamMaster:       *individual people*, each belonging to exactly one department
#
# All "Owner / Module Owner / Technical Owner / Pending With" labels on
# IDRFunctional remain as TEXT for backward compatibility, but are validated
# against TeamMaster.full_name on write. Reads can be enriched with department
# context via join. This is the "hybrid: validated text" pattern.

class DepartmentMaster(Base):
    """The organization-level master. One row per department PER PROJECT."""
    __tablename__ = "department_master"

    # Human-readable PK (e.g. 'BOM-CBS', 'IBL-CBS', 'BOM-DWH').
    dept_id = Column(String(40), primary_key=True, index=True)
    # NEW: Link to owning project (one-to-one per project)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    department_name = Column(String(150), nullable=False, index=True)
    department_email = Column(String(150), nullable=False)
    is_crm = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # department_name unique per project (not globally)
    __table_args__ = (
        UniqueConstraint('project_id', 'department_name', name='uq_project_dept_name'),
    )

    project = relationship("Project", back_populates="departments")
    members = relationship("TeamMaster", back_populates="department", cascade="all, delete-orphan")


class TeamMaster(Base):
    """An individual person scoped to a project through their department.
    Same person (name/email) can exist in multiple projects as separate records.
    """
    __tablename__ = "team_master"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), index=True, nullable=False)          # Removed unique=True
    email = Column(String(150), index=True, nullable=False)              # Removed unique=True
    mobile_phone = Column(String(30), nullable=True)
    dept_id = Column(String(40), ForeignKey("department_master.dept_id", ondelete="CASCADE"), nullable=False, index=True)
    is_crm_user = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Unique email within a department (prevents duplicates within same project-dept)
    __table_args__ = (
        UniqueConstraint('email', 'dept_id', name='uq_email_per_dept'),
    )

    department = relationship("DepartmentMaster", back_populates="members")
class TechnicalDocument(Base):
    """Stores received documents from bank teams for audit trail."""
    __tablename__ = "technical_documents"

    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="CASCADE"), index=True)
    filename = Column(String(255), nullable=False)
    file_data = Column(Text, nullable=False)  # Base64 encoded file content
    file_type = Column(String(50), default="docx")
    received_from = Column(String(150))  # Email sender
    received_at = Column(TIMESTAMP, server_default=func.now())
    notes = Column(Text)


# ============================================================
# MoM MODEL (Touchpoint-Level Minutes of Meeting)
# ============================================================

class MomSession(Base):
    """A per-touchpoint, per-day MoM session. Immutable once SENT."""
    __tablename__ = "mom_sessions"

    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="CASCADE"), nullable=False)
    session_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT")  # DRAFT, GENERATED, SENT
    generated_html = Column(Text, nullable=True)
    sent_at = Column(TIMESTAMP, nullable=True)
    sent_to = Column(JSON, nullable=True)
    created_by = Column(String(100), default="User")
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('touchpoint_id', 'session_date', name='uq_touchpoint_session_date'),
        Index('ix_mom_session_tp_date', 'touchpoint_id', 'session_date'),
    )

    entries = relationship("IDRMomEntry", back_populates="session", cascade="all, delete-orphan")
    discussions = relationship("IDRDiscussionEntry", back_populates="session", cascade="all, delete-orphan")


class IDRMomEntry(Base):
    """A single action-item line in a touchpoint-level MoM."""
    __tablename__ = "idr_mom_entries"

    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("mom_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    description = Column(Text, nullable=False)
    action_point = Column(Text)
    owner = Column(String(100))
    expected_date = Column(Date, nullable=True)
    created_by = Column(String(100), default="User")
    created_at = Column(TIMESTAMP, server_default=func.now())

    session = relationship("MomSession", back_populates="entries")


class IDRDiscussionEntry(Base):
    """A discussion note captured during a touchpoint workshop/meeting."""
    __tablename__ = "idr_discussion_entries"

    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("mom_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    created_by = Column(String(100), default="User")
    created_at = Column(TIMESTAMP, server_default=func.now())

    session = relationship("MomSession", back_populates="discussions")


# ============================================================
# FOLLOW-UP MODEL
# ============================================================

class FollowUpItem(Base):
    """Structured follow-up action items, spawned from MoM or created manually."""
    __tablename__ = "follow_up_items"

    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="CASCADE"), nullable=False)
    source_mom_entry_id = Column(Integer, ForeignKey("idr_mom_entries.id", ondelete="SET NULL"), nullable=True)
    source_session_id = Column(Integer, ForeignKey("mom_sessions.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=False)
    action = Column(Text, nullable=True)
    owner = Column(String(100), nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="OPEN")
    closed_at = Column(TIMESTAMP, nullable=True)
    closed_by = Column(String(100), nullable=True)
    close_note = Column(Text, nullable=True)
    last_nudged_at = Column(Date, nullable=True)
    created_by = Column(String(100), default="User")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_followup_tp_status', 'touchpoint_id', 'status'),
        Index('ix_followup_status_due', 'status', 'due_date'),
        Index('ix_followup_source', 'source_mom_entry_id'),
    )


# ============================================================
# MOCK SERVICE MODEL
# ============================================================

class MockService(Base):
    """Developer utility: stubbed bank API endpoints for integration testing."""
    __tablename__ = "mock_services"

    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id", ondelete="SET NULL"), nullable=True, index=True)
    method_name = Column(String(200), nullable=False, index=True)
    http_method = Column(String(10), nullable=False, default="POST")
    status_code = Column(Integer, nullable=False, default=200)
    content_type = Column(String(100), nullable=False, default="application/json")
    payload = Column(Text, nullable=False)
    created_by = Column(String(100), default="User")
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            'method_name', 'http_method',
            name='uq_mock_method_httpmethod'
        ),
    )
