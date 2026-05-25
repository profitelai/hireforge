"""Apply session routes — create, update, list, and detail for smart-apply sessions."""

import json
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Application, ApplySession, GeneratedCoverLetter, GeneratedCV, Profile
from app.schemas import (
    ApplySessionEntry,
    ApplySessionListResponse,
    CreateApplySessionRequest,
    UpdateApplySessionRequest,
)

router = APIRouter()


def _parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _session_entry(s: ApplySession) -> ApplySessionEntry:
    return ApplySessionEntry(
        id=s.id,
        session_key=s.session_key,
        profile_id=s.profile_id,
        status=s.status,
        job_url=s.job_url,
        company_name=s.company_name,
        role_title=s.role_title,
        location=s.location,
        salary=s.salary,
        job_description=s.job_description,
        match_score=s.match_score,
        fit_analysis=_parse_json(s.fit_analysis),
        config=_parse_json(s.config),
        application_id=s.application_id,
        created_at=s.created_at or datetime.now(UTC),
        updated_at=s.updated_at or datetime.now(UTC),
    )


def _session_detail(s: ApplySession, db: Session) -> ApplySessionEntry:
    entry = _session_entry(s)

    if s.application_id:
        app = db.query(Application).filter_by(id=s.application_id).first()
        if app:
            entry.application = {
                "id": app.id,
                "company_name": app.company_name,
                "role_title": app.role_title,
                "status": app.status,
                "job_url": app.job_url,
                "location": app.location,
                "salary": app.salary,
                "applied_date": app.applied_date.isoformat() if app.applied_date else None,
                "notes": app.notes,
                "created_at": app.created_at.isoformat() if app.created_at else None,
            }

            # Most recent CV for this application
            cv = (
                db.query(GeneratedCV)
                .filter_by(application_id=s.application_id)
                .order_by(GeneratedCV.created_at.desc())
                .first()
            )
            if cv:
                entry.generated_cv = {
                    "id": cv.id,
                    "enhanced": bool(cv.enhanced),
                    "match_score": cv.match_score,
                    "language": cv.language or "en",
                    "created_at": cv.created_at.isoformat() if cv.created_at else None,
                }

            # Most recent CL for this application
            cl = (
                db.query(GeneratedCoverLetter)
                .filter_by(application_id=s.application_id)
                .order_by(GeneratedCoverLetter.created_at.desc())
                .first()
            )
            if cl:
                entry.generated_cl = {
                    "id": cl.id,
                    "tone": cl.tone,
                    "language": cl.language or "en",
                    "cover_letter_text": cl.cover_letter_text[:300] + "..." if len(cl.cover_letter_text) > 300 else cl.cover_letter_text,
                    "created_at": cl.created_at.isoformat() if cl.created_at else None,
                }

    return entry


@router.post("/apply-sessions", response_model=ApplySessionEntry)
def create_session(body: CreateApplySessionRequest, db: Session = Depends(get_db)):
    """Create a new apply session and return a unique session key."""
    # Verify profile exists
    profile = db.query(Profile).filter_by(id=body.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    # Generate unique 8-char key
    for _ in range(10):
        key = secrets.token_urlsafe(6)[:8]
        if not db.query(ApplySession).filter_by(session_key=key).first():
            break

    session = ApplySession(
        session_key=key,
        profile_id=body.profile_id,
        job_url=body.job_url,
        status="in_progress",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_entry(session)


@router.patch("/apply-sessions/{key}", response_model=ApplySessionEntry)
def update_session(key: str, body: UpdateApplySessionRequest, db: Session = Depends(get_db)):
    """Update session fields as the apply workflow progresses."""
    session = db.query(ApplySession).filter_by(session_key=key).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if body.company_name is not None:
        session.company_name = body.company_name
    if body.role_title is not None:
        session.role_title = body.role_title
    if body.location is not None:
        session.location = body.location
    if body.salary is not None:
        session.salary = body.salary
    if body.job_description is not None:
        session.job_description = body.job_description
    if body.match_score is not None:
        session.match_score = body.match_score
    if body.fit_analysis is not None:
        session.fit_analysis = json.dumps(body.fit_analysis)
    if body.config is not None:
        session.config = json.dumps(body.config)
    if body.application_id is not None:
        session.application_id = body.application_id
    if body.status is not None:
        session.status = body.status

    db.commit()
    db.refresh(session)
    return _session_entry(session)


@router.get("/apply-sessions", response_model=ApplySessionListResponse)
def list_sessions(
    profile_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List apply sessions with optional filters."""
    q = db.query(ApplySession)
    if profile_id:
        q = q.filter(ApplySession.profile_id == profile_id)
    if status:
        q = q.filter(ApplySession.status == status)
    total = q.count()
    items = q.order_by(ApplySession.created_at.desc()).offset(offset).limit(limit).all()
    return ApplySessionListResponse(
        items=[_session_entry(s) for s in items],
        total=total,
    )


@router.get("/apply-sessions/{key}", response_model=ApplySessionEntry)
def get_session(key: str, db: Session = Depends(get_db)):
    """Get full session detail including linked application and generated docs."""
    session = db.query(ApplySession).filter_by(session_key=key).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return _session_detail(session, db)


@router.delete("/apply-sessions/{key}")
def delete_session(key: str, db: Session = Depends(get_db)):
    """Delete a session record (does not delete the linked application)."""
    session = db.query(ApplySession).filter_by(session_key=key).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    db.delete(session)
    db.commit()
    return {"ok": True}
