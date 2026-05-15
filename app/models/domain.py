from sqlalchemy import Column, Integer, String, Text, Date, DateTime, JSON, Boolean, ForeignKey, TIMESTAMP
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

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
    
    # --- UPDATED COLUMNS ---
    comment = Column(Text)                     # Strictly for Remarks
    open_pointer_history = Column(Text)        # Strictly for Pointers history
    created_at = Column(TIMESTAMP, server_default=func.now()) 

    touchpoint = relationship("IntegrationTouchpoint", back_populates="action_logs")
class TeamMaster(Base):
    __tablename__ = "team_master"

    id = Column(Integer, primary_key=True, index=True)
    team_name = Column(String, unique=True, index=True, nullable=False)
    contact_email = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

class IDRTechnical(Base):
    """Phase 2: Technical Integration Requirements"""
    __tablename__ = "idr_technical"

    id = Column(Integer, primary_key=True, index=True)
    touchpoint_id = Column(Integer, ForeignKey("integration_touchpoints.id"))
    
    # Workflow & Tracking
    tech_status = Column(String, default="Pending Workshop") 
    pending_with = Column(String) 
    
    # NEW: Project Management Tracking columns
    source_system = Column(String, nullable=True)
    start_date = Column(DateTime, nullable=True)   # Now stores date + time for workshop scheduling
    end_date = Column(DateTime, nullable=True)     # Now stores date + time for workshop scheduling
    
    # Integration Approach (This will start as Null/Unassigned)
    integration_type = Column(String, nullable=True) # "API", "Database", "Batch"
    
    # Dynamic Payload (Stores the specific API/DB/Batch details)
    technical_details = Column(JSON, default={})
    
    # Historical Tracking
    open_pointers = Column(Text)

    # ============================================================
# MOCK SERVICE ENGINE
# ============================================================
class MockService(Base):
    """Stores user-defined mock API responses."""
    __tablename__ = "mock_services"

    id = Column(Integer, primary_key=True, index=True)
    
    # The endpoint path (e.g., 'leads/create')
    method_name = Column(String(200), index=True, nullable=False) 
    
    # Support for different HTTP methods
    http_method = Column(String(10), default="POST", nullable=False)
    
    # Support for testing error codes (200, 400, 500)
    status_code = Column(Integer, default=200, nullable=False)
    
    # Auto-detect JSON or XML
    content_type = Column(String(50), default="application/json")
    
    # The actual response string
    payload = Column(Text, nullable=False)
    
    created_at = Column(TIMESTAMP, server_default=func.now())
    created_by = Column(String(100), default="System")