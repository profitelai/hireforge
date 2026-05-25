from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String, nullable=False, default="Default")
    color = Column(String, nullable=False, default="#6366f1")
    icon = Column(String, nullable=False, default="💼")
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    location = Column(String, nullable=True)
    linkedin = Column(String, nullable=True)
    github = Column(String, nullable=True)
    portfolio = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    work_experience = Column(Text, default="[]")
    education = Column(Text, default="[]")
    skills = Column(Text, default="[]")
    projects = Column(Text, default="[]")
    certifications = Column(Text, default="[]")
    languages = Column(Text, default="[]")
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )



class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class GeneratedCV(Base):
    __tablename__ = "generated_cv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    enhanced = Column(Integer, default=0)  # 0 = false, 1 = true (SQLite bool)
    profile_snapshot = Column(Text, nullable=False)  # JSON string of ProfileData
    profile_id = Column(
        Integer, ForeignKey("profile.id", ondelete="SET NULL"), nullable=True
    )
    application_id = Column(
        Integer, ForeignKey("application.id", ondelete="SET NULL"), nullable=True
    )
    application_status = Column(String, nullable=True, default=None)
    match_score = Column(Integer, nullable=True)
    fit_analysis = Column(Text, nullable=True)
    language = Column(String, nullable=True, default="en")
    job_result_id = Column(
        Integer, ForeignKey("job_search_result.id", ondelete="SET NULL"), nullable=True
    )


class GeneratedCoverLetter(Base):
    __tablename__ = "generated_cover_letter"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    company_name = Column(String, nullable=True)
    role_title = Column(String, nullable=True)
    location = Column(String, nullable=True)
    salary = Column(String, nullable=True)
    job_description = Column(Text, nullable=False)
    extra_context = Column(Text, nullable=True)
    cover_letter_text = Column(Text, nullable=False)
    profile_id = Column(
        Integer, ForeignKey("profile.id", ondelete="SET NULL"), nullable=True
    )
    application_id = Column(
        Integer, ForeignKey("application.id", ondelete="SET NULL"), nullable=True
    )
    job_url = Column(String, nullable=True)
    match_score = Column(Integer, nullable=True)
    fit_analysis = Column(Text, nullable=True)  # JSON string of FitAnalysisResponse
    tone = Column(String, nullable=False, default="professional")
    application_status = Column(String, nullable=True, default=None)
    language = Column(String, nullable=True, default="en")


class Application(Base):
    __tablename__ = "application"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String, nullable=False)
    role_title = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="applied")
    job_url = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    applied_date = Column(Date, nullable=True)
    profile_id = Column(
        Integer, ForeignKey("profile.id", ondelete="SET NULL"), nullable=True
    )
    location = Column(String, nullable=True)
    salary = Column(String, nullable=True)
    job_description = Column(Text, nullable=True)
    resume_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AppSetting(Base):
    __tablename__ = "app_setting"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


class JobSearchResult(Base):
    __tablename__ = "job_search_result"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    scan_url = Column(String, nullable=True)

    company_name = Column(String, nullable=True)
    role_title = Column(String, nullable=True)
    location = Column(String, nullable=True)
    salary = Column(String, nullable=True)
    job_url = Column(String, nullable=True)
    apply_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    easy_apply = Column(Boolean, nullable=False, default=False)
    source = Column(String, nullable=False, default="linkedin")
    posted_at = Column(String, nullable=True)

    match_score = Column(Integer, nullable=True)
    match_data = Column(Text, nullable=True)  # JSON: {recommendation, strengths, missing_skills}

    # pending | scored | approved | skipped | generating | generated | applying | applied | failed
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)

    application_id = Column(
        Integer, ForeignKey("application.id", ondelete="SET NULL"), nullable=True
    )
    profile_id = Column(
        Integer, ForeignKey("profile.id", ondelete="SET NULL"), nullable=True
    )
    cv_id = Column(
        Integer, ForeignKey("generated_cv.id", ondelete="SET NULL"), nullable=True
    )
    cl_id = Column(
        Integer, ForeignKey("generated_cover_letter.id", ondelete="SET NULL"), nullable=True
    )
    session_id = Column(String, nullable=True)  # FK-by-value to AutoApplySession.session_id


class AutoApplySession(Base):
    __tablename__ = "auto_apply_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, nullable=False)
    label = Column(String, nullable=True)
    search_keyword = Column(String, nullable=True)
    location = Column(String, nullable=True)
    source = Column(String, nullable=False, default="linkedin")
    filters_json = Column(Text, nullable=True)   # JSON: {easy_apply_only, remote_only}
    scan_url = Column(String, nullable=True)
    profile_id = Column(
        Integer, ForeignKey("profile.id", ondelete="SET NULL"), nullable=True
    )
    status = Column(String, nullable=False, default="active")  # active | archived
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class InterviewSession(Base):
    __tablename__ = "interview_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    application_id = Column(
        Integer, ForeignKey("application.id", ondelete="SET NULL"), nullable=True
    )
    profile_id = Column(
        Integer, ForeignKey("profile.id", ondelete="SET NULL"), nullable=True
    )
    language = Column(String, nullable=False, default="EN")
    job_description = Column(Text, nullable=True)
    overall_score = Column(Float, nullable=True)
    question_count = Column(Integer, nullable=False, default=0)
    answer_length = Column(String, nullable=True, default="medium")  # short|medium|detailed


class InterviewQuestion(Base):
    __tablename__ = "interview_question"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer, ForeignKey("interview_session.id", ondelete="CASCADE"), nullable=False
    )
    question_index = Column(Integer, nullable=False, default=0)
    question_text = Column(Text, nullable=False)
    model_answer = Column(Text, nullable=True)
    user_answer = Column(Text, nullable=True)
    score = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)  # JSON list
    improvements = Column(Text, nullable=True)  # JSON list
    grammar_errors = Column(Text, nullable=True)  # JSON list
    improved_answer = Column(Text, nullable=True)


class ApplySession(Base):
    __tablename__ = "apply_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_key = Column(String, unique=True, nullable=False)
    profile_id = Column(
        Integer, ForeignKey("profile.id", ondelete="SET NULL"), nullable=True
    )
    # in_progress | completed | partial | abandoned
    status = Column(String, nullable=False, default="in_progress")

    job_url = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    role_title = Column(String, nullable=True)
    location = Column(String, nullable=True)
    salary = Column(String, nullable=True)
    job_description = Column(Text, nullable=True)

    match_score = Column(Integer, nullable=True)
    fit_analysis = Column(Text, nullable=True)  # JSON

    config = Column(Text, nullable=True)  # JSON: {language, tone, cvEnhance, ...}

    application_id = Column(
        Integer, ForeignKey("application.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class LlmUsageLog(Base):
    __tablename__ = "llm_usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    operation = Column(String, nullable=False)

    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    cost = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=True)

    profile_id = Column(
        Integer, ForeignKey("profile.id", ondelete="SET NULL"), nullable=True
    )

    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
