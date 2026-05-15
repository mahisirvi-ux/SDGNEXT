from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.models.domain import MockService

router = APIRouter()

# Schema for incoming data from the UI
class MockCreate(BaseModel):
    method_name: str
    http_method: str = "POST"
    status_code: int = 200
    content_type: str = "application/json"
    payload: str
    created_by: str = "System User"

# ==========================================================
# 1. CREATE MOCK (Fails if method already exists)
# ==========================================================
@router.post("/api/mocks/create")
def create_mock(mock_in: MockCreate, db: Session = Depends(get_db)):
    """Saves a mock response. Fails if the method name already exists."""
    clean_method = mock_in.method_name.strip("/")
    
    # Check if a mock with this exact method and HTTP type already exists
    existing = db.query(MockService).filter(
        MockService.method_name == clean_method,
        MockService.http_method == mock_in.http_method.upper()
    ).first()

    if existing:
        # Prevent Override!
        raise HTTPException(
            status_code=400, 
            detail="Mock with same method name already exists. Kindly change method name."
        )

    # Create new mock
    new_mock = MockService(
        method_name=clean_method,
        http_method=mock_in.http_method.upper(),
        status_code=mock_in.status_code,
        content_type=mock_in.content_type,
        payload=mock_in.payload,
        created_by=mock_in.created_by
    )
    db.add(new_mock)
    db.commit()
    
    return {
        "status": "success", 
        "message": "Mock created successfully!", 
        "mock_url": f"/mock-api/{clean_method}"
    }

# ==========================================================
# 2. LIST/SEARCH MOCKS (Used by the Deployed Mocks Tab)
# ==========================================================
@router.get("/api/mocks/list")
def list_mocks(query: str = "", db: Session = Depends(get_db)):
    """Returns a list of deployed mocks, optionally filtered by method name."""
    if query:
        # Search by partial match on method_name
        mocks = db.query(MockService).filter(MockService.method_name.ilike(f"%{query}%")).all()
    else:
        # Return the 50 most recent if no search query
        mocks = db.query(MockService).order_by(MockService.id.desc()).limit(50).all()
        
    return [{
        "id": m.id,
        "method_name": m.method_name,
        "http_method": m.http_method,
        "status_code": m.status_code,
        "content_type": m.content_type
    } for m in mocks]


# ==========================================================
# 3. THE MAGIC "CATCH-ALL" FAKE SERVER ROUTE
# ==========================================================
@router.api_route("/mock-api/{method_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def serve_mock(method_name: str, request: Request, db: Session = Depends(get_db)):
    """Intercepts hits to /mock-api/... and returns the saved database payload."""
    clean_method = method_name.strip("/")
    req_method = request.method.upper()

    # Find the exact mock for this URL and HTTP Method
    mock = db.query(MockService).filter(
        MockService.method_name == clean_method,
        MockService.http_method == req_method
    ).first()

    if not mock:
        # Fallback: If they hit it with GET but saved it as POST, still try to return it
        mock_fallback = db.query(MockService).filter(MockService.method_name == clean_method).first()
        if mock_fallback:
            mock = mock_fallback
        else:
            raise HTTPException(status_code=404, detail=f"No mock found for endpoint: '{clean_method}'")

    # Return the raw text as a proper HTTP Response
    return Response(
        content=mock.payload, 
        status_code=mock.status_code, 
        media_type=mock.content_type
    )