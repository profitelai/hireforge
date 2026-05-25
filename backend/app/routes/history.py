import json
import logging
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_user_profile_ids, require_llm_config
from app.exceptions import not_found_404
from app.models import Application, GeneratedCoverLetter, GeneratedCV, JobSearchResult, Profile, User
from app.schemas import (
    ATSEnhancement,
    BulkDeleteRequest,
    GeneratedCoverLetterEntry,
    GeneratedCoverLetterListResponse,
    GeneratedCVEntry,
    GeneratedCVListResponse,
    UpdateStatusRequest,
)
from app.services.fit_analysis import analyze_fit
from app.services.llm import (
    OPERATION_COVER_LETTER,
    OPERATION_CV_GENERATION,
    call_llm,
    clean_llm_json,
)
from app.services.prompts import ATS_SYSTEM_PROMPT, COVER_LETTER_SYSTEM_PROMPT, TONE_PROMPTS
from app.utils import batch_load_profiles, format_profile_for_llm, profile_to_schema

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_company(entry: GeneratedCoverLetter) -> str:
    """Extract company name from stored field or job_description."""
    if entry.company_name:
        return entry.company_name
    first_line = re.sub(
        r"^(title|job title|position|role)\s*:\s*",
        "",
        (entry.job_description or "").split("\n")[0].strip(),
        flags=re.IGNORECASE,
    )
    at_match = re.search(r"\bat\s+([^,(\n]+)", first_line, re.IGNORECASE)
    if at_match:
        return at_match.group(1).strip()[:30]
    dash_match = re.search(r"\s[-–]\s*([A-Za-z]\S+)", first_line)
    if dash_match:
        return dash_match.group(1)[:30]
    return first_line[:30] or "Unknown Company"


def _enrich_cv(entry: GeneratedCV, profiles: dict, applications: dict | None = None, job_results: dict | None = None) -> dict:
    p = profiles.get(entry.profile_id) if entry.profile_id else None
    app = (applications or {}).get(entry.application_id) if entry.application_id else None
    # Fall back to auto-apply job_search_result for company/role when no application is linked
    jsr = (job_results or {}).get(entry.id) if not app else None
    fit = None
    if entry.fit_analysis:
        try:
            fit = json.loads(entry.fit_analysis)
        except Exception:
            fit = None
    return {
        "id": entry.id,
        "created_at": entry.created_at,
        "enhanced": bool(entry.enhanced),
        "profile_snapshot": entry.profile_snapshot,
        "application_status": entry.application_status,
        "application_id": entry.application_id,
        "role_title": (app.role_title if app else None) or (jsr.role_title if jsr else None),
        "company_name": (app.company_name if app else None) or (jsr.company_name if jsr else None),
        "profile_id": entry.profile_id,
        "profile_label": p.label if p else None,
        "profile_color": p.color if p else None,
        "profile_icon": p.icon if p else None,
        "match_score": entry.match_score,
        "fit_analysis": fit,
        "language": getattr(entry, "language", None) or "en",
    }


def _enrich_cl(entry: GeneratedCoverLetter, profiles: dict) -> dict:
    p = profiles.get(entry.profile_id) if entry.profile_id else None
    fit = None
    if entry.fit_analysis:
        try:
            fit = json.loads(entry.fit_analysis)
        except Exception:
            fit = None
    return {
        "id": entry.id,
        "created_at": entry.created_at,
        "company_name": entry.company_name,
        "role_title": entry.role_title,
        "location": entry.location,
        "salary": entry.salary,
        "job_description": entry.job_description,
        "extra_context": entry.extra_context,
        "cover_letter_text": entry.cover_letter_text,
        "tone": entry.tone or "professional",
        "job_url": entry.job_url,
        "match_score": entry.match_score,
        "fit_analysis": fit,
        "application_status": entry.application_status,
        "application_id": entry.application_id,
        "profile_id": entry.profile_id,
        "profile_label": p.label if p else None,
        "profile_color": p.color if p else None,
        "profile_icon": p.icon if p else None,
        "language": getattr(entry, "language", None) or "en",
    }


# --- CV history ---


@router.get("/history/cv", response_model=GeneratedCVListResponse)
def list_cv_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    profile_id: int | None = Query(default=None),
    sort: str = Query(default="date_desc"),
    limit: int = Query(default=500),
    offset: int = Query(default=0),
):
    user_pids = get_user_profile_ids(current_user, db)
    q = db.query(GeneratedCV).filter(GeneratedCV.profile_id.in_(user_pids))
    if profile_id is not None:
        q = q.filter(GeneratedCV.profile_id == profile_id)
    if sort == "date_asc":
        q = q.order_by(GeneratedCV.created_at.asc())
    else:
        q = q.order_by(GeneratedCV.created_at.desc())
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    pm = batch_load_profiles(items, db)
    app_ids = {e.application_id for e in items if e.application_id}
    am = {}
    if app_ids:
        for a in db.query(Application).filter(Application.id.in_(app_ids)).all():
            am[a.id] = a
    # Build mapping cv_id → job_search_result for CVs without an application (auto-apply)
    no_app_cv_ids = {e.id for e in items if not e.application_id}
    jm: dict = {}
    if no_app_cv_ids:
        for jsr in db.query(JobSearchResult).filter(JobSearchResult.cv_id.in_(no_app_cv_ids)).all():
            if jsr.cv_id:
                jm[jsr.cv_id] = jsr
    return GeneratedCVListResponse(
        items=[_enrich_cv(e, pm, am, jm) for e in items], total=total
    )


@router.get("/history/cv/{entry_id}", response_model=GeneratedCVEntry)
def get_cv_history_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise not_found_404("CV entry")
    if entry.profile_id not in get_user_profile_ids(current_user, db):
        raise HTTPException(status_code=403, detail="Access denied.")
    jm: dict = {}
    if not entry.application_id:
        jsr = db.query(JobSearchResult).filter_by(cv_id=entry_id).first()
        if jsr:
            jm[entry_id] = jsr
    return _enrich_cv(entry, batch_load_profiles([entry], db), job_results=jm)


@router.delete("/history/cv/{entry_id}", status_code=204)
def delete_cv_history_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise not_found_404("CV entry")
    if entry.profile_id not in get_user_profile_ids(current_user, db):
        raise HTTPException(status_code=403, detail="Access denied.")
    db.delete(entry)
    db.commit()


@router.patch("/history/cv/{entry_id}/status", response_model=GeneratedCVEntry)
def update_cv_status(
    entry_id: int,
    body: UpdateStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise not_found_404("CV entry")
    if entry.profile_id not in get_user_profile_ids(current_user, db):
        raise HTTPException(status_code=403, detail="Access denied.")
    entry.application_status = body.status
    db.commit()
    return _enrich_cv(entry, batch_load_profiles([entry], db))


# --- Cover letter history ---


@router.get("/history/cover-letter", response_model=GeneratedCoverLetterListResponse)
def list_cover_letter_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    profile_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    match_min: int | None = Query(default=None),
    match_max: int | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str = Query(default="date_desc"),
    limit: int = Query(default=500),
    offset: int = Query(default=0),
):
    user_pids = get_user_profile_ids(current_user, db)
    q = db.query(GeneratedCoverLetter).filter(GeneratedCoverLetter.profile_id.in_(user_pids))
    if profile_id is not None:
        q = q.filter(GeneratedCoverLetter.profile_id == profile_id)
    if search:
        term = f"%{search}%"
        q = q.filter(
            GeneratedCoverLetter.company_name.ilike(term)
            | GeneratedCoverLetter.job_description.ilike(term)
        )
    if match_min is not None:
        q = q.filter(GeneratedCoverLetter.match_score >= match_min)
    if match_max is not None:
        q = q.filter(GeneratedCoverLetter.match_score <= match_max)
    if status:
        q = q.filter(GeneratedCoverLetter.application_status == status)
    if sort == "date_asc":
        q = q.order_by(GeneratedCoverLetter.created_at.asc())
    elif sort == "match_desc":
        q = q.order_by(GeneratedCoverLetter.match_score.desc().nullslast())
    elif sort == "company_asc":
        q = q.order_by(GeneratedCoverLetter.company_name.asc().nullslast())
    else:
        q = q.order_by(GeneratedCoverLetter.created_at.desc())
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    pm = batch_load_profiles(items, db)
    return GeneratedCoverLetterListResponse(
        items=[_enrich_cl(e, pm) for e in items], total=total
    )


@router.get(
    "/history/cover-letter/{entry_id}", response_model=GeneratedCoverLetterEntry
)
def get_cover_letter_history_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise not_found_404("Cover letter")
    if entry.profile_id not in get_user_profile_ids(current_user, db):
        raise HTTPException(status_code=403, detail="Access denied.")
    return _enrich_cl(entry, batch_load_profiles([entry], db))


@router.delete("/history/cover-letter/{entry_id}", status_code=204)
def delete_cover_letter_history_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise not_found_404("Cover letter")
    if entry.profile_id not in get_user_profile_ids(current_user, db):
        raise HTTPException(status_code=403, detail="Access denied.")
    db.delete(entry)
    db.commit()


@router.patch(
    "/history/cover-letter/{entry_id}/status", response_model=GeneratedCoverLetterEntry
)
def update_cover_letter_status(
    entry_id: int, body: UpdateStatusRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise not_found_404("Cover letter")
    if entry.profile_id not in get_user_profile_ids(current_user, db):
        raise HTTPException(status_code=403, detail="Access denied.")
    entry.application_status = body.status
    if body.status:
        if entry.application_id:
            # Sync status to the linked Application
            linked = db.query(Application).filter_by(id=entry.application_id).first()
            if linked:
                linked.status = body.status
        else:
            # Auto-create an Application record and link it
            app = Application(
                company_name=entry.company_name or "Unknown",
                role_title=entry.role_title or "",
                location=entry.location,
                salary=entry.salary,
                job_description=entry.job_description,
                status=body.status,
                job_url=entry.job_url,
                profile_id=entry.profile_id,
                applied_date=date.today(),
            )
            db.add(app)
            db.flush()
            entry.application_id = app.id
    # Note: clearing to "—" does not unlink the Application — manage it from Tracker
    db.commit()
    return _enrich_cl(entry, batch_load_profiles([entry], db))


@router.delete("/history/cover-letter")
def bulk_delete_cover_letters(
    body: BulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_pids = get_user_profile_ids(current_user, db)
    deleted = (
        db.query(GeneratedCoverLetter)
        .filter(GeneratedCoverLetter.id.in_(body.ids))
        .filter(GeneratedCoverLetter.profile_id.in_(user_pids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


@router.delete("/history/cv")
def bulk_delete_cvs(
    body: BulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_pids = get_user_profile_ids(current_user, db)
    deleted = (
        db.query(GeneratedCV)
        .filter(GeneratedCV.id.in_(body.ids))
        .filter(GeneratedCV.profile_id.in_(user_pids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


# --- Regeneration endpoints ---


@router.post("/history/regenerate-cl/{cl_id}", response_model=GeneratedCoverLetterEntry)
def regenerate_cover_letter(
    cl_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm: tuple[str, str] = Depends(require_llm_config),
):
    """Generate a new cover letter version from an existing one, including gap fixes, auto-scored."""
    original = db.query(GeneratedCoverLetter).filter_by(id=cl_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    if original.profile_id not in get_user_profile_ids(current_user, db):
        raise HTTPException(status_code=403, detail="Access denied.")

    profile = db.query(Profile).filter_by(id=original.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    provider, api_key = llm
    profile_data = profile_to_schema(profile)

    # Include potential gaps from fit analysis as fit_context
    fit_context = None
    if original.fit_analysis:
        try:
            analysis = json.loads(original.fit_analysis)
            gaps = analysis.get("potential_gaps") or analysis.get("missing_skills") or []
            if gaps:
                gap_text = "; ".join(str(g) for g in gaps[:5])
                fit_context = (
                    f"The previous version was missing these points — address them naturally in this version: {gap_text}"
                )
        except Exception:
            pass

    # Build prompt (mirrors generate.py logic)
    parts = [format_profile_for_llm(profile_data)]
    parts.append(f"\n---\nJOB DESCRIPTION:\n{original.job_description}")
    if original.company_name:
        parts.append(f"\nCOMPANY NAME: {original.company_name}")
    if original.extra_context and original.extra_context.strip():
        parts.append(f"\nSPECIAL INSTRUCTIONS FROM CANDIDATE:\n{original.extra_context.strip()}")
    if fit_context:
        parts.append(
            f"\nAdditional context from the candidate: {fit_context}.\n"
            "Use this to guide emphasis — do not fabricate experience, but frame existing "
            "experience to address these points where honest."
        )
    tone = original.tone or "professional"
    tone_modifier = TONE_PROMPTS.get(tone, TONE_PROMPTS["professional"])
    parts.append(f"\nTONE INSTRUCTION: {tone_modifier}")
    prompt = "\n".join(parts)

    full_text = call_llm(
        prompt,
        system=COVER_LETTER_SYSTEM_PROMPT,
        provider=provider,
        api_key=api_key,
        operation=OPERATION_COVER_LETTER,
        profile_id=original.profile_id,
    )

    new_entry = GeneratedCoverLetter(
        company_name=original.company_name,
        role_title=original.role_title,
        location=original.location,
        salary=original.salary,
        job_description=original.job_description,
        extra_context=original.extra_context,
        cover_letter_text=full_text,
        profile_id=original.profile_id,
        job_url=original.job_url,
        tone=tone,
        application_id=original.application_id,
    )
    db.add(new_entry)
    db.commit()

    # Auto-score the new version
    try:
        profile_json = format_profile_for_llm(profile_data)
        fit = analyze_fit(profile_json, original.job_description, provider, api_key, profile_id=original.profile_id)
        new_entry.match_score = fit.match_score
        new_entry.fit_analysis = json.dumps(fit.model_dump())
        db.commit()
    except Exception as exc:
        logger.warning("Auto-scoring new CL failed: %s", exc)

    pm = {p.id: p for p in db.query(Profile).all()}
    return _enrich_cl(new_entry, pm)


@router.post("/history/regenerate-cv/{cl_id}", response_model=GeneratedCVEntry)
def regenerate_cv_from_cl(
    cl_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm: tuple[str, str] = Depends(require_llm_config),
):
    """Generate a new ATS-enhanced CV version using the job from a cover letter, auto-scored."""
    cl = db.query(GeneratedCoverLetter).filter_by(id=cl_id).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    if cl.profile_id not in get_user_profile_ids(current_user, db):
        raise HTTPException(status_code=403, detail="Access denied.")

    profile = db.query(Profile).filter_by(id=cl.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    provider, api_key = llm
    profile_data = profile_to_schema(profile)

    # ATS-enhance the profile for this specific job
    enhanced = False
    result_profile = profile_data
    try:
        user_prompt = format_profile_for_llm(profile_data)
        user_prompt += f"\n\n---\nTARGET JOB DESCRIPTION:\n{cl.job_description}"
        user_prompt += f"\n\n---\nORIGINAL DATA (use this schema for your JSON output):\n{profile_data.model_dump_json()}"

        llm_output = call_llm(
            user_prompt,
            system=ATS_SYSTEM_PROMPT,
            provider=provider,
            api_key=api_key,
            operation=OPERATION_CV_GENERATION,
            profile_id=cl.profile_id,
        )
        cleaned = clean_llm_json(llm_output)
        ats = ATSEnhancement(**json.loads(cleaned))
        update_fields: dict = {
            "summary": ats.summary,
            "work_experience": ats.work_experience,
        }
        if ats.skills is not None:
            update_fields["skills"] = ats.skills
        result_profile = profile_data.model_copy(update=update_fields)
        enhanced = True
    except Exception as exc:
        logger.warning("ATS enhancement failed, using raw profile: %s", exc)

    new_cv = GeneratedCV(
        enhanced=int(enhanced),
        profile_snapshot=result_profile.model_dump_json(),
        profile_id=cl.profile_id,
        application_id=cl.application_id,
    )
    db.add(new_cv)
    db.commit()

    # Auto-score
    try:
        profile_json = format_profile_for_llm(result_profile)
        fit = analyze_fit(profile_json, cl.job_description, provider, api_key, profile_id=cl.profile_id)
        new_cv.match_score = fit.match_score
        new_cv.fit_analysis = json.dumps(fit.model_dump())
        db.commit()
    except Exception as exc:
        logger.warning("Auto-scoring new CV failed: %s", exc)

    pm = {p.id: p for p in db.query(Profile).all()}
    am = {}
    if new_cv.application_id:
        app_obj = db.query(Application).filter_by(id=new_cv.application_id).first()
        if app_obj:
            am[new_cv.application_id] = app_obj
    # Use company/role from the CL since the CV isn't linked to an app yet
    result = _enrich_cv(new_cv, pm, am)
    if not result.get("company_name"):
        result["company_name"] = cl.company_name
    if not result.get("role_title"):
        result["role_title"] = cl.role_title
    return result
