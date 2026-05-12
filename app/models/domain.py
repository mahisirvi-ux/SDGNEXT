from sqlalchemy import Column, Integer, String, Text, Date, DateTime, JSON, Boolean, ForeignKey, TIMESTAMP
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

    touchpoints = relationship("IntegrationTouchpoint", back_populates="project", cascade="all, delete-orphan")


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
    idr_status = Column(String(50), default="In-Progress")

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
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id"))

    tech_status = Column(String, default="Pending Workshop")
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
    """The organization-level master. One row per department (bank or CRM-side)."""
    __tablename__ = "department_master"

    # Human-readable PK (e.g. 'BNK-CBS', 'BNK-DWH', 'CRM-GENERIC').
    dept_id = Column(String(40), primary_key=True, index=True)

    department_name = Column(String(150), nullable=False, unique=True, index=True)
    department_email = Column(String(150), nullable=False)
    is_crm = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    members = relationship("TeamMaster", back_populates="department", cascade="all, delete-orphan")


class TeamMaster(Base):
    """An individual person who may be referenced as Owner / Pending With / etc.
    Was: {team_name, contact_email}. Now a full identity record.
    See migration file for column rename steps.
    """
    __tablename__ = "team_master"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    mobile_phone = Column(String(30), nullable=True)
    dept_id = Column(String(40), ForeignKey("department_master.dept_id"), nullable=False, index=True)
    is_crm_user = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    department = relationship("DepartmentMaster", back_populates="members")
