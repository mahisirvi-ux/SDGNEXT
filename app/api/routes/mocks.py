from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.core.database import get_db
from app.models.domain import MockService

router = APIRouter()


@router.post("/api/mocks/create")
def create_mock(request_body: dict, db: Session = Depends(get_db)):
    """Creates or updates a mock service endpoint (upsert by touchpoint_id)."""
    method_name = (request_body.get("method_name") or "").strip()
    http_method = (request_body.get("http_method") or "POST").upper().strip()
    status_code = request_body.get("status_code", 200)
    content_type = request_body.get("content_type", "application/json")
    payload = request_body.get("payload", "")
    created_by = request_body.get("created_by", "User")
    touchpoint_id = request_body.get("touchpoint_id", None)

    if not method_name:
        raise HTTPException(status_code=400, detail="method_name is required.")
    if not payload:
        raise HTTPException(status_code=400, detail="payload is required.")

    # Strip leading slashes for consistency
    method_name = method_name.lstrip("/")

    # If touchpoint_id provided, check if a mock already exists for this touchpoint
    existing_for_tp = None
    if touchpoint_id:
        existing_for_tp = db.query(MockService).filter(
            MockService.touchpoint_id == int(touchpoint_id)
        ).first()

    if existing_for_tp:
        # UPDATE existing mock
        existing_for_tp.method_name = method_name
        existing_for_tp.http_method = http_method
        existing_for_tp.status_code = int(status_code)
        existing_for_tp.content_type = content_type
        existing_for_tp.payload = payload
        try:
            db.commit()
            db.refresh(existing_for_tp)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Another mock with this method name already exists. Kindly change method name."
            )
        mock_url = f"/mock-api/{existing_for_tp.method_name}"
        print(f"[{datetime.now()}] Mock updated: {http_method} {mock_url} -> {status_code}")
        return {
            "status": "success",
            "message": f"Mock updated for {http_method} /{method_name}",
            "mock_url": mock_url,
            "id": existing_for_tp.id,
            "updated": True
        }

    # Check uniqueness for new creation (different touchpoint or no touchpoint)
    existing = db.query(MockService).filter(
        MockService.method_name == method_name,
        MockService.http_method == http_method
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Mock with same method name already exists. Kindly change method name."
        )

    new_mock = MockService(
        method_name=method_name,
        http_method=http_method,
        status_code=int(status_code),
        content_type=content_type,
        payload=payload,
        created_by=created_by,
        touchpoint_id=int(touchpoint_id) if touchpoint_id else None
    )

    try:
        db.add(new_mock)
        db.commit()
        db.refresh(new_mock)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Mock with same method name already exists. Kindly change method name."
        )

    mock_url = f"/mock-api/{new_mock.method_name}"
    print(f"[{datetime.now()}] Mock created: {http_method} {mock_url} -> {status_code}")

    return {
        "status": "success",
        "message": f"Mock created for {http_method} /{method_name}",
        "mock_url": mock_url,
        "id": new_mock.id
    }


@router.get("/api/mocks/list")
def list_mocks(db: Session = Depends(get_db)):
    """Lists all deployed mock services."""
    mocks = db.query(MockService).order_by(MockService.created_at.desc()).all()
    return {
        "status": "success",
        "mocks": [
            {
                "id": m.id,
                "method_name": m.method_name,
                "http_method": m.http_method,
                "status_code": m.status_code,
                "content_type": m.content_type,
                "mock_url": f"/mock-api/{m.method_name}",
                "touchpoint_id": m.touchpoint_id,
                "created_by": m.created_by,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in mocks
        ]
    }


@router.get("/api/mocks/by-touchpoint/{tp_id}")
def get_mock_by_touchpoint(tp_id: int, db: Session = Depends(get_db)):
    """Returns mock(s) linked to a specific touchpoint."""
    mocks = db.query(MockService).filter(
        MockService.touchpoint_id == tp_id
    ).order_by(MockService.created_at.desc()).all()

    if not mocks:
        return {"status": "success", "mock": None}

    # Return the most recent one as primary
    m = mocks[0]
    return {
        "status": "success",
        "mock": {
            "id": m.id,
            "method_name": m.method_name,
            "http_method": m.http_method,
            "status_code": m.status_code,
            "content_type": m.content_type,
            "payload": m.payload,
            "mock_url": f"/mock-api/{m.method_name}",
            "created_by": m.created_by,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
    }


@router.api_route("/mock-api/{method_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def serve_mock(method_name: str, request: Request, db: Session = Depends(get_db)):
    """Catch-all endpoint that serves saved mock payloads.

    Matches on method_name only. The stored http_method is metadata
    describing the real bank API — it does NOT restrict access to the
    mock. Any HTTP method can fetch the mock response.
    """
    clean_method = method_name.strip("/")

    mock = db.query(MockService).filter(
        MockService.method_name == clean_method
    ).first()

    if not mock:
        raise HTTPException(
            status_code=404,
            detail=f"No mock found for /{clean_method}"
        )

    return Response(
        content=mock.payload,
        status_code=mock.status_code,
        media_type=mock.content_type
    )
