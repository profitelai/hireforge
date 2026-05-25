// snake_case identifiers in this file mirror the Python backend API contract — intentional.
import { getAuthHeader } from '$lib/auth.svelte';

import type {
    AbTestCvRequest,
    AbTestResponse,
    ApplicationEntry,
    ApplicationFilters,
    ApplicationListResponse,
    ApplySession,
    ApplySessionListResponse,
    CreateApplySessionRequest,
    CoverLetterHistoryFilters,
    InterviewSessionDetail,
    InterviewSessionListResponse,
    CoverLetterPdfRequest,
    CoverLetterRequest,
    CoverLetterResponse,
    CreateApplicationRequest,
    CreateProfileRequest,
    CvHistoryFilters,
    CvPdfRequest,
    FitAnalysisResponse,
    GenerateCvRequest,
    GenerateCvResponse,
    GeneratedCVEntry,
    GeneratedCVListResponse,
    GeneratedCoverLetterEntry,
    GeneratedCoverLetterListResponse,
    IntegrationsResponse,
    LlmUsageFilters,
    LlmUsageListResponse,
    LlmUsageStats,
    ModelsResponse,
    OnboardingStatusResponse,
    PdfRequest,
    ProfileData,
    ProfileListResponse,
    ScrapeAnalyzeResponse,
    ScrapeJobResponse,
    SettingsResponse,
    StatusResponse,
    TestConnectionResponse,
    UpdateApplicationRequest,
    UpdateApplySessionRequest,
    UpdateSettingsRequest,
} from './types';
import { buildQs } from './utils';

// ---------------------------------------------------------------------------
// Base URL — override via VITE_API_BASE_URL env variable for non-localhost envs
// ---------------------------------------------------------------------------
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api';

// ---------------------------------------------------------------------------
// Core fetch helpers
// ---------------------------------------------------------------------------

/** JSON request/response for the vast majority of API calls. */
async function request<T>(path: string, options: RequestInit = {}, fetchFn: typeof fetch = fetch): Promise<T> {
    const res = await fetchFn(`${BASE_URL}${path}`, {
        headers: { 'Content-Type': 'application/json', ...getAuthHeader(), ...options.headers },
        ...options,
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Something went wrong. Please try again.' }));
        throw new Error(err.detail ?? 'Something went wrong. Please try again.');
    }

    if (res.status === 204 || res.headers.get('content-length') === '0') {
        return undefined as T;
    }

    return res.json() as Promise<T>;
}

/** FormData upload — used for file and text CV imports. */
async function requestForm<T>(path: string, body: FormData): Promise<T> {
    const res = await fetch(`${BASE_URL}${path}`, { method: 'POST', body });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to import your CV. Please check the file and try again.' }));
        throw new Error(err.detail ?? 'Failed to import your CV. Please check the file and try again.');
    }
    return res.json() as Promise<T>;
}

/** Blob download — used for PDF generation endpoints. */
async function requestBlob(path: string, options: RequestInit): Promise<Blob> {
    const res = await fetch(`${BASE_URL}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to download. Please try again.' }));
        throw new Error(err.detail ?? 'Failed to download. Please try again.');
    }
    return res.blob();
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export const listProfiles = (fetchFn?: typeof fetch) =>
    request<ProfileListResponse>('/profiles', {}, fetchFn);

export const createProfile = (data: CreateProfileRequest, fetchFn?: typeof fetch) =>
    request<ProfileData>('/profiles', { method: 'POST', body: JSON.stringify(data) }, fetchFn);

export const getProfile = (profileId: number, fetchFn?: typeof fetch) =>
    request<ProfileData>(`/profiles/${profileId}`, {}, fetchFn);

export const saveProfile = (profileId: number, data: ProfileData, fetchFn?: typeof fetch) =>
    request<ProfileData>(`/profiles/${profileId}`, { method: 'PUT', body: JSON.stringify(data) }, fetchFn);

export const deleteProfile = (profileId: number, fetchFn?: typeof fetch) =>
    request<void>(`/profiles/${profileId}`, { method: 'DELETE' }, fetchFn);

export const getOnboardingStatus = (fetchFn?: typeof fetch) =>
    request<OnboardingStatusResponse>('/onboarding', {}, fetchFn);

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

export const getStatus = (fetchFn?: typeof fetch) =>
    request<StatusResponse>('/status', {}, fetchFn);

// ---------------------------------------------------------------------------
// Import CV
// ---------------------------------------------------------------------------

export const importCvFile = (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return requestForm<ProfileData>('/import/cv', form);
};

export const importCvText = (text: string) => {
    const form = new FormData();
    form.append('text', text);
    return requestForm<ProfileData>('/import/cv', form);
};

// ---------------------------------------------------------------------------
// Generate CV
// ---------------------------------------------------------------------------

export const generateCv = (data: GenerateCvRequest) =>
    request<GenerateCvResponse>('/generate/cv', { method: 'POST', body: JSON.stringify(data) });

export const generateCvPdf = (data: CvPdfRequest) =>
    requestBlob('/generate/cv/pdf', { method: 'POST', body: JSON.stringify(data) });

export const generateCvFromJdPdf = async (
    profileId: number,
    options: { file?: File; jdText?: string; companyName?: string; roleTitle?: string; language?: 'en' | 'fr' },
): Promise<{ cv_id: number; application_id: number; enhanced: boolean; company_name: string; role_title: string; profile: any }> => {
    const fd = new FormData();
    fd.append('profile_id', String(profileId));
    fd.append('language', options.language ?? 'en');
    if (options.file) fd.append('file', options.file);
    if (options.jdText) fd.append('jd_text_input', options.jdText);
    if (options.companyName) fd.append('company_name', options.companyName);
    if (options.roleTitle) fd.append('role_title', options.roleTitle);
    const res = await fetch(`${BASE_URL}/generate/cv-from-jd-pdf`, { method: 'POST', body: fd });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail ?? `HTTP ${res.status}`); }
    return res.json();
};

export const generateCvStream = (data: GenerateCvRequest): Promise<Response> =>
    fetch(`${BASE_URL}/generate/cv/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });

export const abTestCv = (data: AbTestCvRequest) =>
    request<AbTestResponse>('/generate/cv/ab-test', { method: 'POST', body: JSON.stringify(data) });

// ---------------------------------------------------------------------------
// Generate Cover Letter
// ---------------------------------------------------------------------------

export const generateCoverLetter = (data: CoverLetterRequest) =>
    request<CoverLetterResponse>('/generate/cover-letter', {
        method: 'POST',
        body: JSON.stringify(data),
    });

export const generateCoverLetterStream = (data: CoverLetterRequest): Promise<Response> =>
    fetch(`${BASE_URL}/generate/cover-letter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });

export const generateCoverLetterPdf = (data: CoverLetterPdfRequest) =>
    requestBlob('/generate/cover-letter/pdf', { method: 'POST', body: JSON.stringify(data) });

// ---------------------------------------------------------------------------
// Generate Bullets / Summary (streaming endpoints)
// ---------------------------------------------------------------------------

export const generateBulletsStream = (
    profile_id: number,
    company: string,
    role: string,
    bullets: string[],
    mode: 'improve' | 'reorganize',
    extra_context?: string
): Promise<Response> =>
    fetch(`${BASE_URL}/generate/bullets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id, company, role, bullets, mode, extra_context }),
    });

export const generateSummaryStream = (profile_id: number, tone: string, extra_context?: string): Promise<Response> =>
    fetch(`${BASE_URL}/generate/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id, tone, extra_context }),
    });

// ---------------------------------------------------------------------------
// Scrape
// ---------------------------------------------------------------------------

export const scrapeJob = (url: string) =>
    request<ScrapeJobResponse>('/scrape/job', { method: 'POST', body: JSON.stringify({ url }) });

export const scrapeAnalyze = (data: { url?: string; text?: string }) =>
    request<ScrapeAnalyzeResponse>('/scrape/analyze', { method: 'POST', body: JSON.stringify(data) });

export const parseJobDescription = (text: string) =>
    request<{ company_name: string | null; role_title: string | null; location: string | null; salary: string | null }>('/scrape/parse', { method: 'POST', body: JSON.stringify({ text }) });

// ---------------------------------------------------------------------------
// Fit Analysis
// ---------------------------------------------------------------------------

export const analyzeFit = (profile_id: number, job_description: string) =>
    request<FitAnalysisResponse>('/analyze/fit', {
        method: 'POST',
        body: JSON.stringify({ profile_id, job_description }),
    });

export const analyzeFitWithCv = (cv_id: number, job_description: string) =>
    request<FitAnalysisResponse>('/analyze/fit-cv', {
        method: 'POST',
        body: JSON.stringify({ cv_id, job_description }),
    });

// ---------------------------------------------------------------------------
// CV History
// ---------------------------------------------------------------------------

export const getCvHistory = (filters: CvHistoryFilters = {}) =>
    request<GeneratedCVListResponse>(`/history/cv${buildQs(filters)}`);

export const getCvHistoryEntry = (id: number) =>
    request<GeneratedCVEntry>(`/history/cv/${id}`);

export const deleteCvHistoryEntry = (id: number) =>
    request<void>(`/history/cv/${id}`, { method: 'DELETE' });

export const updateCvStatus = (id: number, status: string | null) =>
    request<GeneratedCVEntry>(`/history/cv/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
    });

export const bulkDeleteCvs = (ids: number[]) =>
    request<{ deleted: number }>('/history/cv', {
        method: 'DELETE',
        body: JSON.stringify({ ids }),
    });

export const regenerateCl = (cl_id: number) =>
    request<GeneratedCoverLetterEntry>(`/history/regenerate-cl/${cl_id}`, { method: 'POST' });

export const regenerateCv = (cl_id: number) =>
    request<GeneratedCVEntry>(`/history/regenerate-cv/${cl_id}`, { method: 'POST' });

// ---------------------------------------------------------------------------
// Cover Letter History
// ---------------------------------------------------------------------------

export const getCoverLetterHistory = (filters: CoverLetterHistoryFilters = {}) =>
    request<GeneratedCoverLetterListResponse>(`/history/cover-letter${buildQs(filters)}`);

export const getCoverLetterHistoryEntry = (id: number) =>
    request<GeneratedCoverLetterEntry>(`/history/cover-letter/${id}`);

export const deleteCoverLetterHistoryEntry = (id: number) =>
    request<void>(`/history/cover-letter/${id}`, { method: 'DELETE' });

export const updateCoverLetterStatus = (id: number, status: string | null) =>
    request<GeneratedCoverLetterEntry>(`/history/cover-letter/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
    });

export const bulkDeleteCoverLetters = (ids: number[]) =>
    request<{ deleted: number }>('/history/cover-letter', {
        method: 'DELETE',
        body: JSON.stringify({ ids }),
    });

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export const getSettings = () =>
    request<SettingsResponse>('/settings');

export const updateSettings = (data: UpdateSettingsRequest) =>
    request<SettingsResponse>('/settings', { method: 'PUT', body: JSON.stringify(data) });

export const testConnection = (data: UpdateSettingsRequest) =>
    request<TestConnectionResponse>('/settings/test', { method: 'POST', body: JSON.stringify(data) });

export const getModels = () =>
    request<ModelsResponse>('/settings/models');

export const getIntegrations = () =>
    request<IntegrationsResponse>('/settings/integrations');

export const activateProvider = (provider_id: string) =>
    request<SettingsResponse>('/settings/activate', { method: 'PUT', body: JSON.stringify({ provider_id }) });

export const disconnectProvider = (provider_id: string) =>
    request<IntegrationsResponse>(`/settings/integrations/${provider_id}`, { method: 'DELETE' });

// ---------------------------------------------------------------------------
// Applications
// ---------------------------------------------------------------------------

export const listApplications = (filters: ApplicationFilters = {}) =>
    request<ApplicationListResponse>(`/applications${buildQs(filters)}`);

export const createApplication = (data: CreateApplicationRequest) =>
    request<ApplicationEntry>('/applications', { method: 'POST', body: JSON.stringify(data) });

export const getApplication = (id: number) =>
    request<ApplicationEntry>(`/applications/${id}`);

export const updateApplication = (id: number, data: UpdateApplicationRequest) =>
    request<ApplicationEntry>(`/applications/${id}`, { method: 'PATCH', body: JSON.stringify(data) });

export const deleteApplication = (id: number) =>
    request<{ deleted: number }>(`/applications/${id}`, { method: 'DELETE' });

// ---------------------------------------------------------------------------
// LLM Usage
// ---------------------------------------------------------------------------

export const getLlmUsage = (filters?: LlmUsageFilters) => {
    const params = filters ? buildQs(filters) : '';
    return request<LlmUsageListResponse>(`/usage${params}`);
};

export const getLlmUsageStats = () =>
    request<LlmUsageStats>('/usage/stats', { method: 'GET' });

// ---------------------------------------------------------------------------
// Interview Practice
// ---------------------------------------------------------------------------

export interface InterviewQuestion {
    id: number;
    question: string;
    type: string;
    model_answer: string;
    key_points: string[];
}

export interface InterviewQuestionsResponse {
    questions: InterviewQuestion[];
    session_id: number;
    answer_length: string;
}

export interface EvaluateRequest {
    profile_id?: number;
    session_id?: number;
    question_index?: number;
    question: string;
    model_answer: string;
    user_answer: string;
    language: string;
}

export interface EvaluateResponse {
    score: number;
    feedback: string;
    strengths: string[];
    areas_to_improve: string[];
    grammar_errors: string[];
    improved_answer: string;
}

export const generateInterviewQuestions = (
    profile_id: number,
    job_description: string,
    language: string,
    n: number = 5,
    application_id?: number,
    answer_length: string = 'medium',
) =>
    request<InterviewQuestionsResponse>('/interview/questions', {
        method: 'POST',
        body: JSON.stringify({ profile_id, job_description, language, n, application_id, answer_length }),
    });

export const evaluateAnswer = (data: EvaluateRequest) =>
    request<EvaluateResponse>('/interview/evaluate', {
        method: 'POST',
        body: JSON.stringify(data),
    });

export const finishInterviewSession = (session_id: number, overall_score: number) =>
    request<{ ok: boolean }>(`/interview/sessions/${session_id}/finish`, {
        method: 'POST',
        body: JSON.stringify({ session_id, overall_score }),
    });

export async function fetchTTS(text: string, voice?: string, speed?: number): Promise<Blob> {
    // Fall back to stored preference when not explicitly provided
    let resolvedVoice = voice;
    let resolvedSpeed = speed;
    if (!resolvedVoice || resolvedSpeed === undefined) {
        try {
            const raw = typeof localStorage !== 'undefined' ? localStorage.getItem('hireforge_voice') : null;
            const stored = raw ? JSON.parse(raw) : {};
            resolvedVoice = resolvedVoice ?? stored.voice ?? 'onyx';
            resolvedSpeed = resolvedSpeed ?? stored.speed ?? 0.92;
        } catch {
            resolvedVoice = resolvedVoice ?? 'onyx';
            resolvedSpeed = resolvedSpeed ?? 0.92;
        }
    }
    const res = await fetch(`${BASE_URL}/interview/tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: resolvedVoice, speed: resolvedSpeed }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'TTS failed.' }));
        throw new Error(err.detail ?? 'TTS failed.');
    }
    return res.blob();
}

// ---------------------------------------------------------------------------
// Auto-Apply
// ---------------------------------------------------------------------------

export interface JobSearchResultEntry {
    id: number;
    created_at: string;
    scan_url: string | null;
    company_name: string | null;
    role_title: string | null;
    location: string | null;
    salary: string | null;
    job_url: string | null;
    apply_url: string | null;
    description: string | null;
    easy_apply: boolean;
    source: string;
    posted_at: string | null;
    match_score: number | null;
    match_data: string | null;
    status: string;
    error_message: string | null;
    application_id: number | null;
    profile_id: number | null;
    cv_id: number | null;
    cl_id: number | null;
}

export interface ScanRequest {
    url: string;
    profile_id: number;
    max_jobs?: number;
    min_match_score?: number;
    easy_apply_only?: boolean;
    auto_mode?: boolean;
    session_id?: string;
}

export interface AutoApplySessionEntry {
    id: number;
    session_id: string;
    label: string | null;
    search_keyword: string | null;
    location: string | null;
    source: string;
    scan_url: string | null;
    filters_json: string | null;
    profile_id: number | null;
    status: string;
    created_at: string;
    total_jobs: number;
    pending_jobs: number;
    completed_jobs: number;
    generated_resumes: number;
    applied_jobs: number;
}

export interface PreviewJob {
    job_url: string;
    role_title: string | null;
    company_name: string | null;
    location: string | null;
    salary: string | null;
    easy_apply: boolean;
    posted_at: string | null;
    is_duplicate: boolean;
}

export const getLinkedInStatus = () =>
    request<{ connected: boolean; message: string }>('/auto-apply/linkedin-status');

export const connectLinkedIn = (li_at: string) =>
    request<{ connected: boolean; message: string }>('/auto-apply/linkedin-connect', {
        method: 'POST',
        body: JSON.stringify({ li_at }),
    });

export const disconnectLinkedIn = () =>
    request<{ connected: boolean; message: string }>('/auto-apply/linkedin-connect', {
        method: 'DELETE',
    });

export const previewJobs = (data: ScanRequest) =>
    request<{ jobs: PreviewJob[]; total: number; scraped: number }>('/auto-apply/preview', {
        method: 'POST',
        body: JSON.stringify(data),
    });

export const addJobsToQueue = (profile_id: number, scan_url: string, jobs: PreviewJob[]) =>
    request<{ created: number }>('/auto-apply/add', {
        method: 'POST',
        body: JSON.stringify({ profile_id, scan_url, jobs }),
    });

export const scanJobs = (data: ScanRequest) =>
    request<{ scraped: number; created: number; new_ids: number[]; session_id: string }>('/auto-apply/scan', {
        method: 'POST',
        body: JSON.stringify(data),
    });

export const listAutoApplyResults = (profile_id?: number, status?: string, session_id?: string) => {
    const qs = buildQs({ profile_id, status, session_id });
    return request<{ items: JobSearchResultEntry[]; total: number }>(`/auto-apply/results${qs}`);
};

export const listAutoApplySessions = (params?: { profile_id?: number; keyword?: string; status?: string }) => {
    const qs = buildQs(params ?? {});
    return request<{ items: AutoApplySessionEntry[]; total: number }>(`/auto-apply/sessions${qs}`);
};

export const deleteAutoApplySession = (session_id: string) =>
    request<{ ok: boolean }>(`/auto-apply/sessions/${session_id}`, { method: 'DELETE' });

export const listJobCvVersions = (result_id: number) =>
    request<{ items: { id: number; created_at: string; enhanced: boolean; match_score: number | null }[]; total: number }>(
        `/auto-apply/results/${result_id}/cvs`
    );

export const scoreJob = (result_id: number) =>
    request<JobSearchResultEntry>(`/auto-apply/score/${result_id}`, { method: 'POST' });

export const scoreAllPending = (profile_id: number) =>
    request<{ queued: number }>(`/auto-apply/score-all?profile_id=${profile_id}`, { method: 'POST' });

export const updateJobResultStatus = (result_id: number, status: string) =>
    request<JobSearchResultEntry>(`/auto-apply/results/${result_id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
    });

export const applyToJob = (result_id: number, profile_id: number) =>
    request<JobSearchResultEntry>(`/auto-apply/apply/${result_id}`, {
        method: 'POST',
        body: JSON.stringify({ profile_id }),
    });

export const generateCvForJob = (result_id: number) =>
    request<JobSearchResultEntry>(`/auto-apply/generate-cv/${result_id}`, { method: 'POST' });

export const generateClForJob = (result_id: number) =>
    request<JobSearchResultEntry>(`/auto-apply/generate-cl/${result_id}`, { method: 'POST' });

export const enrichJob = (result_id: number) =>
    request<JobSearchResultEntry>(`/auto-apply/enrich/${result_id}`, { method: 'POST' });

// Interview Sessions
export const listInterviewSessions = (params?: { profile_id?: number; application_id?: number; limit?: number; offset?: number }) =>
    request<InterviewSessionListResponse>(`/interview/sessions${buildQs(params ?? {})}`);

export const getInterviewSession = (id: number) =>
    request<InterviewSessionDetail>(`/interview/sessions/${id}`);

export const deleteInterviewSession = (id: number) =>
    request<{ ok: boolean }>(`/interview/sessions/${id}`, { method: 'DELETE' });

// Apply Sessions
export const createApplySession = (body: CreateApplySessionRequest) =>
    request<ApplySession>('/apply-sessions', { method: 'POST', body: JSON.stringify(body) });

export const updateApplySession = (key: string, body: UpdateApplySessionRequest) =>
    request<ApplySession>(`/apply-sessions/${key}`, { method: 'PATCH', body: JSON.stringify(body) });

export const listApplySessions = (params?: { profile_id?: number; status?: string; limit?: number; offset?: number }) =>
    request<ApplySessionListResponse>(`/apply-sessions${buildQs(params ?? {})}`);

export const getApplySession = (key: string) =>
    request<ApplySession>(`/apply-sessions/${key}`);

export const deleteApplySession = (key: string) =>
    request<{ ok: boolean }>(`/apply-sessions/${key}`, { method: 'DELETE' });

export async function transcribeAudio(audioBlob: Blob, language: string): Promise<string> {
    const form = new FormData();
    form.append('audio', audioBlob, 'recording.webm');
    form.append('language', language);
    const res = await fetch(`${BASE_URL}/interview/transcribe`, {
        method: 'POST',
        body: form,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Transcription failed.' }));
        throw new Error(err.detail ?? 'Transcription failed.');
    }
    const data = await res.json();
    return data.text ?? '';
}

// ── Auth ─────────────────────────────────────────────────────────────────
export const authRegister = (data: { email: string; password: string; name?: string }) =>
    request<{ access_token: string; token_type: string; user: { id: number; email: string; name: string } }>('/auth/register', { method: 'POST', body: JSON.stringify(data) });

export const authLogin = (data: { email: string; password: string }) =>
    request<{ access_token: string; token_type: string; user: { id: number; email: string; name: string } }>('/auth/login', { method: 'POST', body: JSON.stringify(data) });

export const authMe = (fetchFn?: typeof fetch) =>
    request<{ id: number; email: string; name: string }>('/auth/me', {}, fetchFn);
