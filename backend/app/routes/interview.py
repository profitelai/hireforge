"""Interview practice API endpoints."""

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_profile_or_404, require_llm_config
from app.models import Application, InterviewQuestion, InterviewSession
from app.services.interview import (
    evaluate_answer,
    generate_questions,
    text_to_speech,
    transcribe_audio,
)
from app.services.settings import get_provider_api_key
from app.utils import format_profile_for_llm, profile_to_schema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview", tags=["interview"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class QuestionsRequest(BaseModel):
    profile_id: int
    job_description: str
    language: str = "EN"
    n: int = 5
    application_id: int | None = None
    answer_length: str = "medium"  # short | medium | detailed


class EvaluateRequest(BaseModel):
    profile_id: int | None = None
    session_id: int | None = None
    question_index: int | None = None
    question: str
    model_answer: str
    user_answer: str
    language: str = "EN"


class TTSRequest(BaseModel):
    text: str
    voice: str = "onyx"
    speed: float = 0.92


class SessionSummaryRequest(BaseModel):
    session_id: int
    overall_score: float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _q_to_dict(q: InterviewQuestion) -> dict:
    return {
        "id": q.id,
        "question_index": q.question_index,
        "question_text": q.question_text,
        "model_answer": q.model_answer,
        "user_answer": q.user_answer,
        "score": q.score,
        "feedback": q.feedback,
        "strengths": json.loads(q.strengths) if q.strengths else [],
        "improvements": json.loads(q.improvements) if q.improvements else [],
        "grammar_errors": json.loads(q.grammar_errors) if q.grammar_errors else [],
        "improved_answer": q.improved_answer,
    }


def _session_to_dict(s: InterviewSession, include_questions: bool = False, db: Session | None = None) -> dict:
    d = {
        "id": s.id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "application_id": s.application_id,
        "profile_id": s.profile_id,
        "language": s.language,
        "overall_score": s.overall_score,
        "question_count": s.question_count,
        "answer_length": getattr(s, "answer_length", "medium") or "medium",
        "job_description": s.job_description if include_questions else None,
    }
    if include_questions and db is not None:
        qs = (
            db.query(InterviewQuestion)
            .filter(InterviewQuestion.session_id == s.id)
            .order_by(InterviewQuestion.question_index)
            .all()
        )
        d["questions"] = [_q_to_dict(q) for q in qs]
        # Enrich with application info if linked
        if s.application_id:
            app = db.get(Application, s.application_id)
            if app:
                d["application"] = {
                    "id": app.id,
                    "company_name": app.company_name,
                    "role_title": app.role_title,
                    "status": app.status,
                }
    return d


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/questions")
def questions(
    body: QuestionsRequest,
    db: Session = Depends(get_db),
    llm=Depends(require_llm_config),
):
    provider, api_key = llm
    profile = get_profile_or_404(body.profile_id, db)
    profile_text = format_profile_for_llm(profile_to_schema(profile))
    n = max(1, min(10, body.n))
    answer_length = body.answer_length if body.answer_length in ("short", "medium", "detailed") else "medium"
    try:
        data = generate_questions(
            profile_text=profile_text,
            job_description=body.job_description,
            language=body.language,
            provider=provider,
            api_key=api_key,
            n=n,
            profile_id=body.profile_id,
            answer_length=answer_length,
        )
        session = InterviewSession(
            application_id=body.application_id,
            profile_id=body.profile_id,
            language=body.language.upper(),
            job_description=body.job_description[:2000] if body.job_description else None,
            question_count=len(data.get("questions", [])),
            answer_length=answer_length,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        data["session_id"] = session.id
        data["answer_length"] = answer_length
        return data
    except Exception as e:
        logger.exception("Interview questions generation failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/evaluate")
def evaluate(
    body: EvaluateRequest,
    db: Session = Depends(get_db),
    llm=Depends(require_llm_config),
):
    provider, api_key = llm
    try:
        result = evaluate_answer(
            question=body.question,
            model_answer=body.model_answer,
            user_answer=body.user_answer,
            language=body.language,
            provider=provider,
            api_key=api_key,
            profile_id=body.profile_id,
        )
        if body.session_id is not None:
            q_record = InterviewQuestion(
                session_id=body.session_id,
                question_index=body.question_index or 0,
                question_text=body.question,
                model_answer=body.model_answer,
                user_answer=body.user_answer,
                score=result.get("score"),
                feedback=result.get("feedback"),
                strengths=json.dumps(result.get("strengths", [])),
                improvements=json.dumps(result.get("areas_to_improve", [])),
                grammar_errors=json.dumps(result.get("grammar_errors", [])),
                improved_answer=result.get("improved_answer"),
            )
            db.add(q_record)
            db.commit()
        return result
    except Exception as e:
        logger.exception("Answer evaluation failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/sessions/{session_id}/finish")
def finish_session(
    session_id: int,
    body: SessionSummaryRequest,
    db: Session = Depends(get_db),
):
    session = db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    session.overall_score = body.overall_score
    db.commit()
    return {"ok": True}


@router.get("/sessions")
def list_sessions(
    application_id: int | None = None,
    profile_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(InterviewSession)
    if application_id is not None:
        q = q.filter(InterviewSession.application_id == application_id)
    if profile_id is not None:
        q = q.filter(InterviewSession.profile_id == profile_id)
    total = q.count()
    sessions = q.order_by(InterviewSession.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [_session_to_dict(s) for s in sessions],
        "total": total,
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return _session_to_dict(session, include_questions=True, db=db)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    db.delete(session)
    db.commit()
    return {"ok": True}


@router.post("/tts")
def tts(body: TTSRequest, db: Session = Depends(get_db)):
    """Convert text to speech using OpenAI TTS. Returns MP3 audio bytes."""
    openai_key = get_provider_api_key(db, "openai")
    if not openai_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key not configured. Add it in Settings → Integrations.",
        )
    speed = max(0.5, min(1.5, body.speed))
    try:
        audio_bytes = text_to_speech(body.text, openai_key, body.voice, speed)
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        logger.exception("TTS failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Form(default="EN"),
    db: Session = Depends(get_db),
):
    """Transcribe uploaded audio using Whisper. Returns {text: string}."""
    openai_key = get_provider_api_key(db, "openai")
    if not openai_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key not configured. Add it in Settings → Integrations.",
        )
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    try:
        text = transcribe_audio(
            audio_bytes=audio_bytes,
            filename=audio.filename or "recording.webm",
            openai_api_key=openai_key,
            language=language,
        )
        return {"text": text}
    except Exception as e:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
