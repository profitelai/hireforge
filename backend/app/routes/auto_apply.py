"""Auto-apply routes: scan, score, approve/skip, and submit applications."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_llm_config
from app.models import Application, AutoApplySession, GeneratedCoverLetter, GeneratedCV, JobSearchResult, Profile
from app.schemas import (
    ATSEnhancement,
    ApplyRequest,
    AutoApplySessionEntry,
    JobSearchResultEntry,
    JobSearchResultListResponse,
    ScanRequest,
    UpdateJobResultRequest,
)
from app.services.auto_apply import auto_apply, scrape_linkedin_job_urls
from app.services.fit_analysis import analyze_fit
from app.services.llm import OPERATION_COVER_LETTER, OPERATION_CV_GENERATION, call_llm, clean_llm_json, stream_llm
from app.services.prompts import ATS_SYSTEM_PROMPT, COVER_LETTER_SYSTEM_PROMPT, TONE_PROMPTS
from app.services.settings import (
    clear_linkedin_session,
    get_linkedin_li_at,
    get_linkedin_session,
    get_llm_api_base,
    get_llm_config as _get_llm_config_raw,
    save_linkedin_session,
)
from app.utils import format_profile_for_llm, profile_to_schema

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_linkedin_slug(url: str) -> tuple[str | None, str | None]:
    """Extract (role_title, company_name) from a LinkedIn job URL slug.

    e.g. /jobs/view/content-strategist-at-macy-s-4415392006
    → ("Content Strategist", "Macy S")
    """
    import re
    m = re.search(r"/jobs/view/(.+?)-(\d+)/?$", url or "")
    if not m:
        return None, None
    slug = m.group(1)
    at_idx = slug.find("-at-")
    if at_idx == -1:
        return None, None
    role = " ".join(w.capitalize() for w in slug[:at_idx].split("-") if w)
    company = " ".join(w.capitalize() for w in slug[at_idx + 4:].split("-") if w)
    return role or None, company or None


async def fetch_job_description(url: str) -> str | None:
    """Fetch a job description. For LinkedIn, tries the unauthenticated guest API first, then Jina.ai."""
    import re as _re
    import httpx

    # LinkedIn guest API — works without authentication
    if url and "linkedin.com" in url:
        m = _re.search(r"/jobs/view/(?:[^/]+-)?(\d{7,})", url)
        if m:
            job_id = m.group(1)
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(
                        f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}",
                        headers={"User-Agent": "Mozilla/5.0 (compatible)"},
                        timeout=25,
                        follow_redirects=True,
                    )
                    if r.status_code == 200 and len(r.text) > 200:
                        # Strip HTML tags
                        text = _re.sub(r"<[^>]+>", " ", r.text)
                        text = _re.sub(r"\s+", " ", text).strip()
                        if len(text) > 200:
                            logger.info("LinkedIn guest API succeeded for job_id=%s", job_id)
                            return text[:8000]
            except Exception as exc:
                logger.warning("LinkedIn guest API failed for %s: %s", url, exc)

    # Fallback: Jina.ai
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"https://r.jina.ai/{url}", timeout=25)
            if r.status_code == 200 and len(r.text) > 200:
                return r.text[:8000]
    except Exception as exc:
        logger.warning("fetch_job_description (jina) failed for %s: %s", url, exc)
    return None


# ── Keyword patching ──────────────────────────────────────────────────────────


def _patch_missing_keywords(ats: ATSEnhancement, missing_kws: list[str]) -> ATSEnhancement:
    """
    Deterministic safety net: after LLM generation, verify every missing keyword
    appears somewhere in the CV. Any that don't are force-added to the skills list.

    This guarantees ATS scanner coverage regardless of LLM compliance.
    Skills are the safest insertion point — ATS scanners read them, and adding
    a platform/domain term to skills is standard practice in ATS-optimized resumes.
    """
    if not missing_kws:
        return ats

    existing_skills = list(ats.skills or [])
    bullets_text = " ".join(
        b.lower()
        for exp in (ats.work_experience or [])
        for b in (exp.bullets or [])
    )
    full_cv_text = (
        f"{(ats.summary or '').lower()} "
        f"{' '.join(s.lower() for s in existing_skills)} "
        f"{bullets_text}"
    )

    to_add = [kw for kw in missing_kws if kw.lower() not in full_cv_text]

    if not to_add:
        return ats

    logger.info(
        "Keyword patcher: force-adding %d keyword(s) to skills that LLM missed: %s",
        len(to_add),
        to_add,
    )

    # Insert after the first 3 existing skills so top skills stay prominent
    splice = min(3, len(existing_skills))
    updated_skills = existing_skills[:splice] + to_add + existing_skills[splice:]

    return ATSEnhancement(
        summary=ats.summary,
        work_experience=ats.work_experience,
        skills=updated_skills,
    )


def _entry(r: JobSearchResult) -> JobSearchResultEntry:
    return JobSearchResultEntry.model_validate(r)


def _parse_search_params(url: str) -> tuple[str | None, str | None]:
    """Extract (keyword, location) from a LinkedIn search URL query string."""
    from urllib.parse import urlparse, parse_qs
    try:
        qs = parse_qs(urlparse(url).query)
        keyword = qs.get("keywords", [""])[0].replace("+", " ").strip() or None
        location = qs.get("location", [""])[0].replace("+", " ").strip() or None
        return keyword, location
    except Exception:
        return None, None


def _make_session_id(keyword: str | None, location: str | None) -> str:
    """Create a human-readable session ID: seo-director-montreal-20260522-a91x"""
    import re as _re
    import uuid as _uuid
    from datetime import datetime, UTC

    def slugify(s: str) -> str:
        s = _re.sub(r"[^\w\s-]", "", s.lower().strip())
        return _re.sub(r"[\s_]+", "-", s).strip("-")[:20]

    parts = []
    if keyword:
        parts.append(slugify(keyword))
    if location:
        parts.append(slugify(location))
    parts.append(datetime.now(UTC).strftime("%Y%m%d"))
    parts.append(str(_uuid.uuid4())[:4])
    return "-".join(filter(None, parts)) or str(_uuid.uuid4())[:12]


def _session_label(keyword: str | None, location: str | None, url: str = "") -> str:
    """Build a display label for a session."""
    parts = [p for p in [keyword, location] if p]
    if parts:
        return " · ".join(parts)
    # Fallback: extract from URL
    kw, loc = _parse_search_params(url)
    parts = [p for p in [kw, loc] if p]
    return " · ".join(parts) if parts else (url[:50] + "…") if len(url) > 50 else url


# ── Auto-apply session routes ─────────────────────────────────────────────────


@router.get("/auto-apply/sessions")
def list_sessions(
    profile_id: int | None = None,
    keyword: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """List all auto-apply scan sessions with job counts and filters."""
    q = db.query(AutoApplySession)
    if profile_id:
        q = q.filter(AutoApplySession.profile_id == profile_id)
    if status and status != "all":
        q = q.filter(AutoApplySession.status == status)
    if keyword:
        kw = f"%{keyword.lower()}%"
        q = q.filter(
            AutoApplySession.label.ilike(kw)
            | AutoApplySession.search_keyword.ilike(kw)
            | AutoApplySession.location.ilike(kw)
        )
    sessions = q.order_by(AutoApplySession.created_at.desc()).all()

    items = []
    for s in sessions:
        base = db.query(JobSearchResult).filter_by(session_id=s.session_id)
        total = base.count()
        completed = base.filter(JobSearchResult.status.in_(["cl_ready", "applied"])).count()
        pending = (
            db.query(JobSearchResult)
            .filter(
                JobSearchResult.session_id == s.session_id,
                ~JobSearchResult.status.in_(["cl_ready", "applied", "skipped", "failed"]),
            )
            .count()
        )
        resumes = (
            db.query(JobSearchResult)
            .filter(JobSearchResult.session_id == s.session_id, JobSearchResult.cv_id.isnot(None))
            .count()
        )
        applied = (
            db.query(JobSearchResult)
            .filter(JobSearchResult.session_id == s.session_id, JobSearchResult.status == "applied")
            .count()
        )
        items.append(
            AutoApplySessionEntry(
                id=s.id,
                session_id=s.session_id,
                label=s.label,
                search_keyword=s.search_keyword,
                location=s.location,
                source=s.source or "linkedin",
                scan_url=s.scan_url,
                filters_json=s.filters_json,
                profile_id=s.profile_id,
                status=s.status,
                created_at=s.created_at,
                total_jobs=total,
                pending_jobs=pending,
                completed_jobs=completed,
                generated_resumes=resumes,
                applied_jobs=applied,
            )
        )
    return {"items": items, "total": len(items)}


@router.delete("/auto-apply/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """Delete a scan session and all its job results."""
    s = db.query(AutoApplySession).filter_by(session_id=session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found.")
    db.query(JobSearchResult).filter_by(session_id=session_id).delete()
    db.delete(s)
    db.commit()
    return {"ok": True}


# ── LinkedIn session status ───────────────────────────────────────────────────


@router.get("/auto-apply/linkedin-status")
def linkedin_status(db: Session = Depends(get_db)):
    """Check whether a valid (authenticated) LinkedIn session exists."""
    li_at = get_linkedin_li_at(db)
    if li_at:
        return {"connected": True, "message": "LinkedIn connected."}
    return {"connected": False, "message": "No authenticated LinkedIn session. Go to Settings → LinkedIn."}


class LinkedInConnectRequest(BaseModel):
    li_at: str | None = None
    storage_state: dict | None = None


@router.post("/auto-apply/linkedin-connect")
def linkedin_connect(body: LinkedInConnectRequest, db: Session = Depends(get_db)):
    """Save a LinkedIn session. Accepts either a full Playwright storage_state or a bare li_at cookie."""
    import json as _json

    if body.storage_state:
        cookies = body.storage_state.get("cookies", [])
        li_at = next((c["value"] for c in cookies if c["name"] == "li_at"), None)
        if not li_at:
            raise HTTPException(status_code=400, detail="storage_state does not contain an li_at cookie — make sure you are logged in.")
        # Store the full session (all cookies + origins) so LinkedIn validation passes
        from app.services.settings import set_setting
        set_setting(db, "linkedin_session_json", _json.dumps(body.storage_state))
    elif body.li_at:
        save_linkedin_session(db, body.li_at.strip())
    else:
        raise HTTPException(status_code=400, detail="Provide either storage_state or li_at.")
    return {"connected": True, "message": "LinkedIn connected successfully."}


@router.delete("/auto-apply/linkedin-connect")
def linkedin_disconnect(db: Session = Depends(get_db)):
    """Remove the stored LinkedIn session."""
    clear_linkedin_session(db)
    return {"connected": False, "message": "LinkedIn disconnected."}


# ── Preview (dry-run — no DB save) ───────────────────────────────────────────


@router.post("/auto-apply/preview")
async def preview_jobs(body: ScanRequest, db: Session = Depends(get_db)):
    """
    Extract job URLs from a LinkedIn search page and return stubs for review.
    Does NOT save to DB. Uses the existing per-job scraper for details (via /enrich).
    """
    profile = db.query(Profile).filter_by(id=body.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    linkedin_session = get_linkedin_session(db)
    try:
        job_urls = await scrape_linkedin_job_urls(body.url, max_jobs=body.max_jobs, storage_state=linkedin_session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {e}")

    existing_urls: set[str] = {
        r[0] for r in db.query(JobSearchResult.job_url).filter(
            JobSearchResult.profile_id == body.profile_id
        ).all() if r[0]
    }
    app_urls: set[str] = {
        r[0] for r in db.query(Application.job_url).filter(
            Application.profile_id == body.profile_id
        ).all() if r[0]
    }
    skip_urls = existing_urls | app_urls

    preview = [
        {"job_url": u, "is_duplicate": u in skip_urls}
        for u in job_urls
    ]
    return {"jobs": preview, "total": len(preview), "scraped": len(job_urls)}


# ── Scan ─────────────────────────────────────────────────────────────────────


@router.post("/auto-apply/scan")
async def scan_jobs(body: ScanRequest, db: Session = Depends(get_db)):
    """
    Extract job URLs from a LinkedIn search page and save URL stubs to the queue.
    Details (company, title, description) are filled in later via /enrich/{id}.
    Each scan creates (or reuses) an AutoApplySession so results are addressable by URL.
    """
    import uuid as _uuid

    profile = db.query(Profile).filter_by(id=body.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    linkedin_session = get_linkedin_session(db)
    try:
        job_urls = await scrape_linkedin_job_urls(body.url, max_jobs=body.max_jobs, storage_state=linkedin_session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {e}")

    # Resolve keyword / location from explicit params or by parsing the URL
    keyword = body.search_keyword or None
    location = body.location or None
    if not keyword or not location:
        kw_url, loc_url = _parse_search_params(body.url)
        keyword = keyword or kw_url
        location = location or loc_url

    # Resolve or create a session
    session_id = body.session_id
    if session_id:
        existing_session = db.query(AutoApplySession).filter_by(session_id=session_id).first()
    else:
        existing_session = None

    if not existing_session:
        session_id = _make_session_id(keyword, location)
        label = _session_label(keyword, location, body.url)
        db.add(AutoApplySession(
            session_id=session_id,
            label=label,
            search_keyword=keyword,
            location=location,
            source="linkedin",
            scan_url=body.url,
            filters_json=json.dumps({"easy_apply_only": body.easy_apply_only}),
            profile_id=body.profile_id,
            status="active",
        ))
        db.flush()

    existing_urls: set[str] = {
        r[0] for r in db.query(JobSearchResult.job_url).filter(
            JobSearchResult.profile_id == body.profile_id
        ).all() if r[0]
    }
    app_urls: set[str] = {
        r[0] for r in db.query(Application.job_url).filter(
            Application.profile_id == body.profile_id
        ).all() if r[0]
    }
    skip_urls = existing_urls | app_urls

    created = 0
    new_ids: list[int] = []
    for job_url in job_urls:
        if not job_url or job_url in skip_urls:
            continue
        record = JobSearchResult(
            scan_url=body.url,
            job_url=job_url,
            source="linkedin",
            status="pending",
            profile_id=body.profile_id,
            session_id=session_id,
        )
        db.add(record)
        db.flush()
        new_ids.append(record.id)
        skip_urls.add(job_url)
        created += 1

    db.commit()
    return {"scraped": len(job_urls), "created": created, "new_ids": new_ids, "session_id": session_id}


# ── Add selected preview jobs to queue ───────────────────────────────────────


class AddJobsRequest(BaseModel):
    profile_id: int
    scan_url: str
    jobs: list[dict]  # list of preview job dicts to save


@router.post("/auto-apply/add")
def add_jobs_to_queue(body: AddJobsRequest, db: Session = Depends(get_db)):
    """Save a subset of preview jobs (user-selected) to the queue."""
    existing_urls: set[str] = {
        r[0] for r in db.query(JobSearchResult.job_url).filter(
            JobSearchResult.profile_id == body.profile_id
        ).all() if r[0]
    }
    app_urls: set[str] = {
        r[0] for r in db.query(Application.job_url).filter(
            Application.profile_id == body.profile_id
        ).all() if r[0]
    }
    skip_urls = existing_urls | app_urls

    created = 0
    for j in body.jobs:
        job_url = j.get("job_url") or ""
        if not job_url or job_url in skip_urls:
            continue
        record = JobSearchResult(
            scan_url=body.scan_url,
            company_name=j.get("company_name"),
            role_title=j.get("role_title"),
            location=j.get("location"),
            salary=j.get("salary"),
            job_url=job_url,
            easy_apply=bool(j.get("easy_apply")),
            source="linkedin",
            posted_at=j.get("posted_at"),
            status="pending",
            profile_id=body.profile_id,
        )
        db.add(record)
        skip_urls.add(job_url)
        created += 1

    db.commit()
    return {"created": created}


# ── Results list ─────────────────────────────────────────────────────────────


@router.get("/auto-apply/results", response_model=JobSearchResultListResponse)
def list_results(
    profile_id: int | None = None,
    status: str | None = None,
    session_id: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(JobSearchResult)
    if profile_id:
        q = q.filter(JobSearchResult.profile_id == profile_id)
    if status:
        q = q.filter(JobSearchResult.status == status)
    if session_id:
        q = q.filter(JobSearchResult.session_id == session_id)
    q = q.order_by(JobSearchResult.created_at.desc())
    items = q.all()
    return JobSearchResultListResponse(items=[_entry(r) for r in items], total=len(items))


# ── Enrich: fetch full job details via existing per-job scraper ───────────────


@router.post("/auto-apply/enrich/{result_id}", response_model=JobSearchResultEntry)
async def enrich_job(result_id: int, db: Session = Depends(get_db)):
    """
    Fetch full job details for a pending result using the same scraper as
    'Add Job from URL'. Populates company_name, role_title, location, salary,
    and description. Falls back gracefully on failure.
    """
    import httpx
    from app.services.scraper import scrape_job_url

    record = db.query(JobSearchResult).filter_by(id=result_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Result not found.")
    if not record.job_url:
        raise HTTPException(status_code=400, detail="No URL to scrape.")

    try:
        async with httpx.AsyncClient() as client:
            scraped = await scrape_job_url(record.job_url, client)

        if scraped.company_name:
            record.company_name = scraped.company_name
        if scraped.role_title:
            record.role_title = scraped.role_title
        if scraped.location:
            record.location = scraped.location
        if scraped.salary:
            record.salary = scraped.salary
        record.description = scraped.job_description
        record.source = scraped.source
    except Exception as exc:
        logger.warning("Enrich failed for result %d: %s", result_id, exc)
        record.error_message = str(exc)

    # Fallback: parse role/company from LinkedIn URL slug when scraping has no data
    if not record.role_title or not record.company_name:
        slug_role, slug_company = _parse_linkedin_slug(record.job_url or "")
        if slug_role and not record.role_title:
            record.role_title = slug_role
        if slug_company and not record.company_name:
            record.company_name = slug_company

    # Reset failed status to pending so the job can be scored
    if record.status == "failed" and (record.description or record.role_title):
        record.status = "pending"

    db.commit()
    db.refresh(record)
    return _entry(record)


# ── Score individual job ──────────────────────────────────────────────────────


@router.post("/auto-apply/score/{result_id}", response_model=JobSearchResultEntry)
async def score_job(result_id: int, db: Session = Depends(get_db)):
    """Fetch description and run fit analysis for one job result."""
    record = db.query(JobSearchResult).filter_by(id=result_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Result not found.")

    profile = db.query(Profile).filter_by(id=record.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    provider, api_key = require_llm_config(db)

    record.status = "scoring"
    db.commit()

    try:
        if not record.description and record.job_url:
            desc = await fetch_job_description(record.job_url)
            if desc:
                record.description = desc
                db.commit()

        if not record.description:
            record.status = "failed"
            record.error_message = "Could not fetch job description."
            db.commit()
            return _entry(record)

        profile_data = profile_to_schema(profile)
        profile_json = format_profile_for_llm(profile_data)

        result = analyze_fit(
            profile_json,
            record.description,
            provider,
            api_key,
            profile_id=record.profile_id,
        )

        record.match_score = result.match_score
        record.match_data = json.dumps({
            "pros": result.pros,
            "cons": result.cons,
            "missing_keywords": result.missing_keywords,
            "red_flags": result.red_flags,
            "suggested_emphasis": result.suggested_emphasis,
        })
        record.status = "scored"
    except Exception as e:
        record.status = "failed"
        record.error_message = str(e)
        logger.exception("Score job %d failed", result_id)

    db.commit()
    return _entry(record)


# ── Score all pending ─────────────────────────────────────────────────────────


@router.post("/auto-apply/score-all")
async def score_all_pending(profile_id: int, db: Session = Depends(get_db)):
    """Score all pending results for a profile (background)."""
    pending = (
        db.query(JobSearchResult)
        .filter(JobSearchResult.profile_id == profile_id, JobSearchResult.status == "pending")
        .all()
    )
    ids = [r.id for r in pending]

    async def _run():
        for rid in ids:
            try:
                _db = next(get_db())
                rec = _db.query(JobSearchResult).filter_by(id=rid).first()
                if rec:
                    profile = _db.query(Profile).filter_by(id=rec.profile_id).first()
                    provider, api_key = require_llm_config(_db)
                    rec.status = "scoring"
                    _db.commit()

                    if not rec.description and rec.job_url:
                        desc = await fetch_job_description(rec.job_url)
                        if desc:
                            rec.description = desc
                            _db.commit()

                    if not rec.description:
                        rec.status = "failed"
                        rec.error_message = "Could not fetch description."
                        _db.commit()
                        continue

                    profile_data = profile_to_schema(profile)
                    profile_json = format_profile_for_llm(profile_data)
                    result = analyze_fit(profile_json, rec.description, provider, api_key, profile_id=rec.profile_id)
                    rec.match_score = result.match_score
                    rec.match_data = json.dumps({
                        "pros": result.pros,
                        "cons": result.cons,
                        "missing_keywords": result.missing_keywords,
                        "red_flags": result.red_flags,
                    })
                    rec.status = "scored"
                    _db.commit()
            except Exception as e:
                logger.exception("Score-all failed for id %d: %s", rid, e)

    asyncio.create_task(_run())
    return {"queued": len(ids)}


# ── Approve / Skip ────────────────────────────────────────────────────────────


@router.patch("/auto-apply/results/{result_id}", response_model=JobSearchResultEntry)
def update_result_status(
    result_id: int,
    body: UpdateJobResultRequest,
    db: Session = Depends(get_db),
):
    record = db.query(JobSearchResult).filter_by(id=result_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Result not found.")
    if body.status not in ("approved", "skipped", "pending"):
        raise HTTPException(status_code=400, detail="status must be approved, skipped, or pending.")
    record.status = body.status
    db.commit()
    return _entry(record)


# ── Apply ─────────────────────────────────────────────────────────────────────


@router.post("/auto-apply/apply/{result_id}", response_model=JobSearchResultEntry)
async def apply_to_job(
    result_id: int,
    body: ApplyRequest,
    db: Session = Depends(get_db),
):
    """Auto-fill and submit the application form for an approved job."""
    record = db.query(JobSearchResult).filter_by(id=result_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Result not found.")

    profile = db.query(Profile).filter_by(id=body.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    apply_url = record.apply_url or record.job_url
    if not apply_url:
        raise HTTPException(status_code=400, detail="No apply URL for this job.")

    record.status = "applying"
    db.commit()

    name_parts = (profile.name or "").split(" ", 1)
    first = name_parts[0]
    last = name_parts[1] if len(name_parts) > 1 else ""

    result = await auto_apply(
        apply_url=apply_url,
        first_name=first,
        last_name=last,
        email=profile.email or "",
        phone=profile.phone,
        resume_pdf=b"",
        cover_letter=None,
    )

    if result.get("ok"):
        record.status = "applied"
        app = Application(
            company_name=record.company_name or "",
            role_title=record.role_title or "",
            status="applied",
            job_url=record.job_url,
            profile_id=body.profile_id,
            location=record.location,
            salary=record.salary,
            job_description=record.description,
        )
        db.add(app)
        db.flush()
        record.application_id = app.id
    else:
        record.status = "failed"
        record.error_message = result.get("message")

    db.commit()
    return _entry(record)


# ── Generate tailored CV for a job result ─────────────────────────────────────


@router.post("/auto-apply/generate-cv/{result_id}", response_model=JobSearchResultEntry)
def generate_cv_for_job(result_id: int, db: Session = Depends(get_db)):
    """Generate an ATS-optimised CV tailored to the job description and link it to the result."""
    record = db.query(JobSearchResult).filter_by(id=result_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Result not found.")

    profile = db.query(Profile).filter_by(id=record.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    if not record.description:
        raise HTTPException(status_code=400, detail="Job description not fetched yet — score the job first.")

    provider, api_key = _get_llm_config_raw(db)
    api_base = get_llm_api_base(db, provider)
    profile_data = profile_to_schema(profile)

    record.status = "generating"
    db.commit()

    enhanced = False
    result_profile = profile_data

    from app.services.settings import NO_API_KEY_PROVIDERS, provider_from_model
    provider_ok = bool(provider and (api_key or provider_from_model(provider) in NO_API_KEY_PROVIDERS))
    if provider_ok:
        try:
            user_prompt = format_profile_for_llm(profile_data)
            user_prompt += f"\n\n---\nTARGET JOB DESCRIPTION:\n{record.description}"

            # Inject missing keywords so the LLM can intelligently surface implied skills
            match_data = json.loads(record.match_data or "{}")
            missing_kws = match_data.get("missing_keywords", [])
            if missing_kws:
                user_prompt += (
                    f"\n\n---\nMISSING KEYWORDS (identified by ATS gap analysis):\n"
                    + "\n".join(f"- {kw}" for kw in missing_kws)
                    + "\n\nFor each missing keyword above, follow the MISSING KEYWORDS — INTELLIGENT INCORPORATION rules in the system prompt. "
                    "Add adjacent/implied skills to the skills list and naturally weave methodologies into existing bullets where they honestly apply. "
                    "Never fabricate experience that is not in the profile."
                )

            user_prompt += f"\n\n---\nORIGINAL DATA (use this schema for your JSON output):\n{profile_data.model_dump_json()}"
            llm_output = call_llm(
                user_prompt,
                system=ATS_SYSTEM_PROMPT,
                provider=provider,
                api_key=api_key,
                operation=OPERATION_CV_GENERATION,
                profile_id=record.profile_id,
                api_base=api_base,
                timeout=270,
            )
            cleaned = clean_llm_json(llm_output)
            ats = ATSEnhancement(**json.loads(cleaned))
            # Deterministic safety net: force any still-missing keywords into skills
            ats = _patch_missing_keywords(ats, missing_kws)
            update_fields: dict = {
                "summary": ats.summary,
                "work_experience": ats.work_experience,
            }
            if ats.skills is not None:
                update_fields["skills"] = ats.skills
            result_profile = profile_data.model_copy(update=update_fields)
            enhanced = True
        except Exception as exc:
            logger.warning("CV generation for job %d failed: %s", result_id, exc)

    entry = GeneratedCV(
        enhanced=int(enhanced),
        profile_snapshot=result_profile.model_dump_json(),
        profile_id=record.profile_id,
        job_result_id=record.id,
    )
    db.add(entry)
    db.flush()

    record.cv_id = entry.id

    # Re-score using the enhanced profile so the score reflects the tailored CV
    if enhanced and provider and api_key and record.description:
        try:
            enhanced_json = format_profile_for_llm(result_profile)
            new_result = analyze_fit(enhanced_json, record.description, provider, api_key, profile_id=record.profile_id)
            record.match_score = new_result.match_score
            record.match_data = json.dumps({
                "pros": new_result.pros,
                "cons": new_result.cons,
                "missing_keywords": new_result.missing_keywords,
                "red_flags": new_result.red_flags,
                "suggested_emphasis": new_result.suggested_emphasis,
            })
        except Exception as exc:
            logger.warning("Re-score after CV generation failed for job %d: %s", result_id, exc)

    record.status = "generated"
    db.commit()
    return _entry(record)


# ── List resume versions for a job result ─────────────────────────────────────


@router.get("/auto-apply/results/{result_id}/cvs")
def list_cv_versions(result_id: int, db: Session = Depends(get_db)):
    """Return all generated CVs linked to this job result, newest first."""
    cvs = (
        db.query(GeneratedCV)
        .filter_by(job_result_id=result_id)
        .order_by(GeneratedCV.created_at.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": cv.id,
                "created_at": cv.created_at,
                "enhanced": bool(cv.enhanced),
                "match_score": cv.match_score,
            }
            for cv in cvs
        ],
        "total": len(cvs),
    }


# ── Generate cover letter for a job result ────────────────────────────────────


@router.post("/auto-apply/generate-cl/{result_id}", response_model=JobSearchResultEntry)
async def generate_cl_for_job(result_id: int, db: Session = Depends(get_db)):
    """Generate a tailored cover letter for a job result and link it."""
    record = db.query(JobSearchResult).filter_by(id=result_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Result not found.")

    profile = db.query(Profile).filter_by(id=record.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    if not record.description:
        raise HTTPException(status_code=400, detail="Job description missing — score the job first.")

    provider, api_key = _get_llm_config_raw(db)
    api_base = get_llm_api_base(db, provider)
    from app.services.settings import NO_API_KEY_PROVIDERS, provider_from_model as _pfm
    if not provider or (not api_key and _pfm(provider) not in NO_API_KEY_PROVIDERS):
        raise HTTPException(status_code=400, detail="LLM not configured.")

    profile_data = profile_to_schema(profile)

    # Build prompt
    parts = [format_profile_for_llm(profile_data)]
    parts.append(f"\n---\nJOB DESCRIPTION:\n{record.description}")
    if record.company_name:
        parts.append(f"\nCOMPANY NAME: {record.company_name}")
    tone_modifier = TONE_PROMPTS.get("professional", "")
    parts.append(f"\nTONE INSTRUCTION: {tone_modifier}")
    prompt = "\n".join(parts)

    accumulated = []
    try:
        async for chunk in stream_llm(
            prompt,
            system=COVER_LETTER_SYSTEM_PROMPT,
            provider=provider,
            api_key=api_key,
            operation=OPERATION_COVER_LETTER,
            profile_id=record.profile_id,
            api_base=api_base,
            timeout=270,
        ):
            accumulated.append(chunk)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cover letter generation failed: {exc}")

    full_text = "".join(accumulated)
    entry = GeneratedCoverLetter(
        company_name=record.company_name,
        role_title=record.role_title,
        location=record.location,
        salary=record.salary,
        job_description=record.description,
        cover_letter_text=full_text,
        profile_id=record.profile_id,
        job_url=record.job_url,
        tone="professional",
    )
    db.add(entry)
    db.flush()

    record.cl_id = entry.id
    record.status = "cl_ready"
    db.commit()
    return _entry(record)
