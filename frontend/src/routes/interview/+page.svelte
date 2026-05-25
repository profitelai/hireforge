<script lang="ts">
  import { page } from '$app/state';
  import { activeProfile } from '$lib/activeProfile.svelte';
  import {
    evaluateAnswer,
    fetchTTS,
    finishInterviewSession,
    generateInterviewQuestions,
    getApplication,
    listApplications,
    listInterviewSessions,
    transcribeAudio,
    type ApplicationEntry,
    type EvaluateResponse,
    type InterviewQuestion,
  } from '$lib/api';
  import { getTTSCache, getUserRec, recKey, saveUserRec, setTTSCache, ttsKey } from '$lib/audioCache';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { Button } from '$lib/components/ui/button';
  import { Card, CardContent } from '$lib/components/ui/card';
  import { Label } from '$lib/components/ui/label';
  import { Textarea } from '$lib/components/ui/textarea';
  import { toastState } from '$lib/toast.svelte';
  import { voiceSettings } from '$lib/voiceSettings.svelte';
  import { errorMessage, formatDateShort } from '$lib/utils';
  import {
    BookOpen,
    CheckCircle,
    ChevronRight,
    CircleCheck,
    History,
    Mic,
    MicOff,
    Play,
    RefreshCw,
    RotateCcw,
    Square,
    Volume2,
    X,
  } from '@lucide/svelte';

  let { data } = $props();
  const isOnboarded = $derived(data.isOnboarded);

  // ── Setup state ────────────────────────────────────────────────────────────
  type Phase = 'setup' | 'loading' | 'session' | 'done';
  let phase = $state<Phase>('setup');

  let language = $state<'EN' | 'FR'>('EN');
  let numQuestions = $state(5);
  let answerLength = $state<'short' | 'medium' | 'detailed'>('medium');
  let playbackSpeed = $state(1.0);
  let jobDescription = $state('');
  let prefillCompany = $state('');
  let prefillRole = $state('');
  let prefillAppId = $state<number | null>(null);

  // ── Job picker ──────────────────────────────────────────────────────────────
  let applications = $state<ApplicationEntry[]>([]);
  let selectedAppId = $state<number | ''>('');

  $effect(() => {
    listApplications({ limit: 50, sort: 'date_desc' }).then(r => { applications = r.items; }).catch(() => {});
  });

  function handleJobSelect(id: number | '') {
    selectedAppId = id;
    if (!id) { jobDescription = ''; prefillCompany = ''; prefillRole = ''; prefillAppId = null; return; }
    const found = applications.find(a => a.id === id);
    if (!found) return;
    prefillAppId = id;
    prefillCompany = found.company_name;
    prefillRole = found.role_title;
    if (found.job_description) jobDescription = found.job_description;
  }

  // ── Past sessions ───────────────────────────────────────────────────────────
  type SessionSummary = { id: number; created_at: string; language: string; overall_score: number | null; question_count: number; application_id: number | null; answer_length?: string | null };
  let pastSessions = $state<SessionSummary[]>([]);
  let showPastSessions = $state(false);

  $effect(() => {
    const ap = activeProfile.current;
    listInterviewSessions({ profile_id: ap?.id ?? undefined, limit: 10 })
      .then(r => { pastSessions = r.items as SessionSummary[]; })
      .catch(() => {});
  });

  async function resumeSession(targetSessionId: number) {
    const ap = activeProfile.current;
    if (!ap) return;
    const detail = await import('$lib/api').then(m => m.getInterviewSession(targetSessionId)).catch(() => null);
    if (!detail) { toastState.error('Could not load session.'); return; }
    const firstUnanswered = (detail.questions?.length ?? 0) < detail.question_count ? (detail.questions?.length ?? 0) : 0;
    if (!detail.job_description) { toastState.error('No job description saved for this session.'); return; }
    jobDescription = detail.job_description;
    language = detail.language as 'EN' | 'FR';
    answerLength = (detail.answer_length as 'short' | 'medium' | 'detailed') || 'medium';
    prefillAppId = detail.application_id;
    phase = 'loading';
    try {
      const resp = await generateInterviewQuestions(ap.id, detail.job_description, detail.language, detail.question_count, detail.application_id ?? undefined, answerLength);
      questions = resp.questions;
      sessionId = resp.session_id ?? null;
      resetSessionState(firstUnanswered);
      phase = 'session';
      showPastSessions = false;
      toastState.success(`Resumed from question ${firstUnanswered + 1}.`);
    } catch (e) {
      toastState.error(`Failed: ${errorMessage(e)}`);
      phase = 'setup';
    }
  }

  $effect(() => {
    const appId = page.url.searchParams.get('app_id');
    if (!appId) return;
    prefillAppId = Number(appId);
    selectedAppId = Number(appId);
    getApplication(Number(appId)).then(app => {
      if (app.job_description) jobDescription = app.job_description;
      if (app.company_name) prefillCompany = app.company_name;
      if (app.role_title) prefillRole = app.role_title;
    }).catch(() => {});
  });

  // ── Session state ──────────────────────────────────────────────────────────
  let questions = $state<InterviewQuestion[]>([]);
  let sessionId = $state<number | null>(null);
  let scores = $state<number[]>([]);
  let currentIdx = $state(0);
  let showModelAnswer = $state(false);

  type SubPhase = 'idle' | 'playing' | 'recording' | 'transcribing' | 'evaluating' | 'evaluated';
  let subPhase = $state<SubPhase>('idle');

  let transcription = $state('');
  let evaluation = $state<EvaluateResponse | null>(null);

  // ── Recording ──────────────────────────────────────────────────────────────
  let mediaRecorder = $state<MediaRecorder | null>(null);
  let audioChunks = $state<Blob[]>([]);
  let recordSeconds = $state(0);
  let recordTimer: ReturnType<typeof setInterval> | null = null;

  // ── User recording playback per question ────────────────────────────────────
  // In-memory for current session; also persisted to IndexedDB.
  let userRecordingBlobs = new Map<number, Blob>();
  let userRecordingLoaded = $state<Set<number>>(new Set()); // which idxes have a saved recording

  // ── TTS listen counter per question ────────────────────────────────────────
  let modelAnswerListenCount = $state<Record<number, number>>({});
  const MAX_FREE_PLAYS = 3; // after this the answer is always served from cache

  // ── Sentence drill state ────────────────────────────────────────────────────
  type DrillPhase = 'idle' | 'listening' | 'recording' | 'transcribing' | 'result';
  let drillSentence = $state<string | null>(null);
  let drillPhase = $state<DrillPhase>('idle');
  let drillTranscription = $state('');
  let drillMatch = $state<boolean | null>(null);
  let drillAudioChunks: Blob[] = [];
  let drillRecorder: MediaRecorder | null = null;
  let drillRecordSeconds = $state(0);
  let drillTimer: ReturnType<typeof setInterval> | null = null;
  let drillAudio: HTMLAudioElement | null = null;

  const currentQ = $derived(questions[currentIdx] ?? null);
  const progress = $derived(questions.length ? Math.round(((currentIdx + (subPhase === 'evaluated' ? 1 : 0)) / questions.length) * 100) : 0);

  // ── TTS playback with cache ────────────────────────────────────────────────
  let currentAudio: HTMLAudioElement | null = null;

  async function playTTS(text: string, speedOverride?: number): Promise<void> {
    stopAudio();
    const voice = voiceSettings.current.voice;
    const speed = speedOverride ?? (voiceSettings.current.speed * playbackSpeed);
    const key = ttsKey(text, voice, speed);

    subPhase = 'playing';
    try {
      let blob = await getTTSCache(key);
      if (!blob) {
        blob = await fetchTTS(text, voice, speed);
        setTTSCache(key, blob); // fire-and-forget
      }
      const url = URL.createObjectURL(blob);
      currentAudio = new Audio(url);
      await new Promise<void>((resolve, reject) => {
        currentAudio!.onended = () => { URL.revokeObjectURL(url); resolve(); };
        currentAudio!.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Audio error')); };
        currentAudio!.play().catch(reject);
      });
    } catch (e) {
      toastState.error(`Audio error: ${errorMessage(e)}`);
    } finally {
      subPhase = 'idle';
    }
  }

  async function playModelAnswer() {
    if (!currentQ) return;
    const count = (modelAnswerListenCount[currentIdx] ?? 0) + 1;
    modelAnswerListenCount = { ...modelAnswerListenCount, [currentIdx]: count };
    await playTTS(currentQ.model_answer, 0.85);
  }

  function stopAudio() {
    currentAudio?.pause();
    currentAudio = null;
    drillAudio?.pause();
    drillAudio = null;
  }

  // ── User recording ─────────────────────────────────────────────────────────
  function bestRecordingMimeType(): string {
    const preferred = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
    for (const t of preferred) {
      if (MediaRecorder.isTypeSupported(t)) return t;
    }
    return '';
  }

  async function startRecording() {
    stopAudio();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = bestRecordingMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      audioChunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks = [...audioChunks, e.data]; };
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        clearInterval(recordTimer!);
        recordTimer = null;
        await handleTranscribe();
      };
      mediaRecorder = recorder;
      recorder.start(250);
      subPhase = 'recording';
      recordSeconds = 0;
      recordTimer = setInterval(() => { recordSeconds += 1; }, 1000);
    } catch {
      toastState.error('Microphone access denied. Please allow mic access and try again.');
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
      mediaRecorder = null;
    }
  }

  async function handleTranscribe() {
    subPhase = 'transcribing';
    try {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      // Save to memory + IndexedDB
      userRecordingBlobs.set(currentIdx, blob);
      const rKey = recKey(sessionId, currentIdx);
      saveUserRec(rKey, blob); // fire-and-forget
      userRecordingLoaded = new Set([...userRecordingLoaded, currentIdx]);

      const text = await transcribeAudio(blob, language);
      transcription = text;
      subPhase = 'idle';
    } catch (e) {
      toastState.error(`Transcription failed: ${errorMessage(e)}`);
      subPhase = 'idle';
    }
  }

  function playUserRecording() {
    const blob = userRecordingBlobs.get(currentIdx);
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.play().catch(() => URL.revokeObjectURL(url));
  }

  // ── Sentence drill ─────────────────────────────────────────────────────────
  function splitSentences(text: string): string[] {
    const raw = text.match(/[^.!?…]+[.!?…]+(?:\s|$)?/g) ?? [text];
    return raw.map(s => s.trim()).filter(s => s.length > 8);
  }

  function normText(s: string): string {
    return s.toLowerCase().replace(/[^a-zàâçéèêëîïôùûüÿæœ\s]/g, '').replace(/\s+/g, ' ').trim();
  }

  function similarity(a: string, b: string): number {
    const sa = normText(a), sb = normText(b);
    if (!sa || !sb) return 0;
    const words_a = new Set(sa.split(' '));
    const words_b = sb.split(' ');
    const hits = words_b.filter(w => words_a.has(w)).length;
    return hits / Math.max(words_a.size, words_b.length);
  }

  function openDrill(sentence: string) {
    drillSentence = sentence;
    drillPhase = 'idle';
    drillTranscription = '';
    drillMatch = null;
  }

  function closeDrill() {
    drillSentence = null;
    drillPhase = 'idle';
    drillTranscription = '';
    drillMatch = null;
    stopDrillRecording();
  }

  async function playDrillSentence() {
    if (!drillSentence) return;
    drillPhase = 'listening';
    const voice = voiceSettings.current.voice;
    const speed = 0.82; // slightly slower for learning
    const key = ttsKey(drillSentence, voice, speed);
    try {
      let blob = await getTTSCache(key);
      if (!blob) {
        blob = await fetchTTS(drillSentence, voice, speed);
        setTTSCache(key, blob);
      }
      const url = URL.createObjectURL(blob);
      drillAudio = new Audio(url);
      await new Promise<void>((resolve) => {
        drillAudio!.onended = () => { URL.revokeObjectURL(url); resolve(); };
        drillAudio!.onerror = () => { URL.revokeObjectURL(url); resolve(); };
        drillAudio!.play().catch(() => resolve());
      });
    } catch {
      // silent fail
    } finally {
      drillPhase = 'idle';
    }
  }

  async function startDrillRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = bestRecordingMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      drillAudioChunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) drillAudioChunks = [...drillAudioChunks, e.data]; };
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        clearInterval(drillTimer!);
        drillTimer = null;
        drillPhase = 'transcribing';
        try {
          const blob = new Blob(drillAudioChunks, { type: 'audio/webm' });
          const text = await transcribeAudio(blob, language);
          drillTranscription = text;
          drillMatch = similarity(drillSentence ?? '', text) >= 0.6;
          drillPhase = 'result';
        } catch {
          drillPhase = 'idle';
        }
      };
      drillRecorder = recorder;
      recorder.start(250);
      drillPhase = 'recording';
      drillRecordSeconds = 0;
      drillTimer = setInterval(() => { drillRecordSeconds += 1; }, 1000);
    } catch {
      toastState.error('Microphone access denied.');
    }
  }

  function stopDrillRecording() {
    if (drillRecorder && drillRecorder.state !== 'inactive') {
      drillRecorder.stop();
      drillRecorder = null;
    }
    clearInterval(drillTimer!);
    drillTimer = null;
  }

  // ── Interview flow ─────────────────────────────────────────────────────────
  async function startInterview() {
    const ap = activeProfile.current;
    if (!ap) return;
    if (!jobDescription.trim()) {
      toastState.error('Please enter a job description to generate relevant questions.');
      return;
    }
    phase = 'loading';
    try {
      const resp = await generateInterviewQuestions(ap.id, jobDescription.trim(), language, numQuestions, prefillAppId ?? undefined, answerLength);
      questions = resp.questions;
      sessionId = resp.session_id ?? null;
      resetSessionState(0);
      phase = 'session';
    } catch (e) {
      toastState.error(`Failed to generate questions: ${errorMessage(e)}`);
      phase = 'setup';
    }
  }

  function resetSessionState(startIdx = 0) {
    scores = [];
    currentIdx = startIdx;
    transcription = '';
    evaluation = null;
    showModelAnswer = false;
    subPhase = 'idle';
    modelAnswerListenCount = {};
    userRecordingBlobs = new Map();
    userRecordingLoaded = new Set();
    drillSentence = null;
    drillPhase = 'idle';
    drillTranscription = '';
    drillMatch = null;
  }

  async function handleEvaluate() {
    if (!currentQ || !transcription.trim()) return;
    const ap = activeProfile.current;
    subPhase = 'evaluating';
    try {
      const result = await evaluateAnswer({
        profile_id: ap?.id,
        session_id: sessionId ?? undefined,
        question_index: currentIdx,
        question: currentQ.question,
        model_answer: currentQ.model_answer,
        user_answer: transcription,
        language,
      });
      evaluation = result;
      scores = [...scores, result.score];
      subPhase = 'evaluated';
    } catch (e) {
      toastState.error(`Evaluation failed: ${errorMessage(e)}`);
      subPhase = 'idle';
    }
  }

  function nextQuestion() {
    if (currentIdx + 1 >= questions.length) {
      stopAudio();
      finishSession();
      phase = 'done';
      return;
    }
    drillSentence = null;
    currentIdx += 1;
    transcription = '';
    evaluation = null;
    showModelAnswer = false;
    subPhase = 'idle';
  }

  async function finishSession() {
    if (!sessionId || scores.length === 0) return;
    const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
    finishInterviewSession(sessionId, avg).catch(() => {});
  }

  function reset() {
    stopAudio();
    closeDrill();
    phase = 'setup';
    questions = [];
    sessionId = null;
    resetSessionState(0);
  }

  function scoreColor(score: number) {
    if (score >= 80) return 'text-green-600 dark:text-green-400';
    if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-500';
  }

  function scoreBg(score: number) {
    if (score >= 80) return 'bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-800';
    if (score >= 60) return 'bg-yellow-50 border-yellow-200 dark:bg-yellow-950/30 dark:border-yellow-800';
    return 'bg-red-50 border-red-200 dark:bg-red-950/30 dark:border-red-800';
  }

  const recordLabel = $derived(
    recordSeconds < 60
      ? `${recordSeconds}s`
      : `${Math.floor(recordSeconds / 60)}m${recordSeconds % 60}s`
  );

  const drillRecordLabel = $derived(
    drillRecordSeconds < 60 ? `${drillRecordSeconds}s` : `${Math.floor(drillRecordSeconds / 60)}m${drillRecordSeconds % 60}s`
  );

  // Sentences to drill from evaluation
  const drillableSentences = $derived(
    evaluation
      ? splitSentences(evaluation.improved_answer || currentQ?.model_answer || '').slice(0, 5)
      : []
  );
</script>

{#if !isOnboarded}
  <EmptyState
    icon="user"
    title="Profile required"
    description="Create a profile to start interview practice."
    action={{ label: 'Get started', href: '/onboarding' }}
  />
{:else}
  <PageHeader
    title={prefillRole && prefillCompany ? `Interview — ${prefillRole} @ ${prefillCompany}` : 'Interview Practice'}
    description="AI-powered coaching with voice questions, model answers, live scoring, and sentence-level drill."
  />

  <!-- ── SETUP ─────────────────────────────────────────────────────────────── -->
  {#if phase === 'setup'}
    <div class="max-w-2xl space-y-6">

      {#if pastSessions.length > 0}
        <Card>
          <CardContent class="pt-5 space-y-3">
            <button
              onclick={() => showPastSessions = !showPastSessions}
              class="w-full flex items-center justify-between gap-2 text-sm font-semibold"
            >
              <span class="flex items-center gap-2"><History class="w-4 h-4 text-primary" /> Past Sessions ({pastSessions.length})</span>
              <span class="text-xs text-muted-foreground">{showPastSessions ? 'Hide' : 'Show'}</span>
            </button>
            {#if showPastSessions}
              <div class="space-y-2 mt-2">
                {#each pastSessions as s}
                  {@const app = applications.find(a => a.id === s.application_id)}
                  <div class="flex items-center gap-3 p-2.5 rounded-lg border border-border hover:bg-accent/30 transition-colors">
                    <div class="flex-1 min-w-0">
                      <p class="text-xs font-bold truncate">{app ? `${app.role_title} @ ${app.company_name}` : 'General Practice'}</p>
                      <p class="text-[10px] text-muted-foreground mt-0.5">{s.created_at.slice(0, 10)} · {s.language} · {s.question_count} questions</p>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                      {#if s.overall_score !== null}
                        <span class="text-xs font-bold {s.overall_score >= 80 ? 'text-green-600' : s.overall_score >= 60 ? 'text-yellow-600' : 'text-red-500'}">{s.overall_score}/100</span>
                      {:else}
                        <span class="text-[10px] text-muted-foreground">No score</span>
                      {/if}
                      <Button size="sm" variant="outline" class="h-7 text-xs" onclick={() => resumeSession(s.id)}>
                        <BookOpen class="w-3 h-3 mr-1" /> Resume
                      </Button>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </CardContent>
        </Card>
      {/if}

      {#if applications.length > 0}
        <Card>
          <CardContent class="pt-5 space-y-2">
            <Label>Practice for a specific job</Label>
            <select
              class="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm"
              value={selectedAppId}
              onchange={(e) => handleJobSelect(Number((e.target as HTMLSelectElement).value) || '')}
            >
              <option value="">— General practice (no specific job) —</option>
              {#each applications as a}
                <option value={a.id}>{a.role_title || 'Unknown Role'} @ {a.company_name} ({a.status})</option>
              {/each}
            </select>
            {#if selectedAppId && !jobDescription}
              <p class="text-xs text-yellow-600 dark:text-yellow-400">This job has no description yet — questions will be generic. Add one in the <a href="/pipeline/{selectedAppId}" class="underline">job pipeline</a>.</p>
            {/if}
          </CardContent>
        </Card>
      {/if}

      <Card>
        <CardContent class="pt-6 space-y-3">
          <Label>Language</Label>
          <div class="flex gap-3">
            {#each [{ value: 'EN', label: '🇺🇸 English' }, { value: 'FR', label: '🇨🇦 Français' }] as opt}
              <button
                onclick={() => language = opt.value as 'EN' | 'FR'}
                class="flex-1 py-2.5 rounded-lg border-2 text-sm font-medium transition-colors {language === opt.value
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border hover:border-primary/40'}"
              >
                {opt.label}
              </button>
            {/each}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent class="pt-6 space-y-3">
          <Label for="jd">Job Description</Label>
          <Textarea
            id="jd"
            placeholder="Paste the job posting here — the coach will generate questions tailored to this role and your profile."
            bind:value={jobDescription}
            rows={8}
          />
        </CardContent>
      </Card>

      <Card>
        <CardContent class="pt-6 space-y-3">
          <Label>Number of Questions</Label>
          <div class="flex gap-2">
            {#each [3, 5, 7, 10] as n}
              <button
                onclick={() => numQuestions = n}
                class="px-4 py-2 rounded-lg border-2 text-sm font-medium transition-colors {numQuestions === n
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border hover:border-primary/40'}"
              >
                {n}
              </button>
            {/each}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent class="pt-6 space-y-4">
          <!-- Answer length -->
          <div class="space-y-2">
            <Label>Answer Length</Label>
            <div class="grid grid-cols-3 gap-2">
              {#each [{ v: 'short', label: 'Short', desc: '~50 words, quick' }, { v: 'medium', label: 'Medium', desc: '~120 words, STAR' }, { v: 'detailed', label: 'Detailed', desc: '~220 words, full' }] as opt}
                <button
                  onclick={() => answerLength = opt.v as 'short' | 'medium' | 'detailed'}
                  class="flex flex-col items-start px-3 py-2.5 rounded-lg border-2 text-left transition-colors
                    {answerLength === opt.v ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/40'}"
                >
                  <span class="text-sm font-semibold {answerLength === opt.v ? 'text-primary' : ''}">{opt.label}</span>
                  <span class="text-[10px] text-muted-foreground">{opt.desc}</span>
                </button>
              {/each}
            </div>
          </div>
          <!-- Playback speed -->
          <div class="space-y-2">
            <Label>AI Voice Speed</Label>
            <div class="flex gap-2">
              {#each [{ v: 0.75, label: 'Slow' }, { v: 1.0, label: 'Normal' }, { v: 1.15, label: 'Fast' }] as opt}
                <button
                  onclick={() => playbackSpeed = opt.v}
                  class="flex-1 py-2 rounded-lg border-2 text-xs font-semibold transition-colors
                    {playbackSpeed === opt.v ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:border-primary/40'}"
                >
                  {opt.label}
                </button>
              {/each}
            </div>
            <p class="text-[11px] text-muted-foreground">Slow mode helps with pronunciation practice.</p>
          </div>
        </CardContent>
      </Card>

      <div class="flex items-center gap-3">
        <Button onclick={startInterview} class="flex-1" size="lg">
          Start Interview Session
        </Button>
        <a href="/interview/sessions" class="flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-colors text-muted-foreground shrink-0">
          <History class="w-4 h-4" />
          History
        </a>
      </div>
    </div>

  {:else if phase === 'loading'}
    <div class="flex flex-col items-center justify-center py-24 gap-4 text-muted-foreground">
      <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
      <p class="text-sm">Generating {numQuestions} questions tailored to your profile...</p>
    </div>

  {:else if phase === 'session' && currentQ}
    <div class="max-w-2xl space-y-5">

      <!-- Progress -->
      <div class="space-y-1.5">
        <div class="flex justify-between text-xs text-muted-foreground">
          <span>Question {currentIdx + 1} of {questions.length}</span>
          <span>{progress}%</span>
        </div>
        <div class="w-full h-1.5 bg-muted rounded-full overflow-hidden">
          <div class="h-full bg-primary rounded-full transition-all duration-500" style="width: {progress}%"></div>
        </div>
      </div>

      <!-- Question card -->
      <Card>
        <CardContent class="pt-6 space-y-4">
          <div class="flex items-start gap-3">
            <span class="mt-0.5 shrink-0 text-xs font-semibold px-2 py-0.5 rounded bg-primary/10 text-primary uppercase">
              {currentQ.type}
            </span>
            <p class="text-base font-medium leading-relaxed">{currentQ.question}</p>
          </div>

          <div class="flex gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onclick={() => playTTS(currentQ.question, 1.0)}
              disabled={subPhase === 'playing' || subPhase === 'recording'}
            >
              <Volume2 class="w-3.5 h-3.5 mr-1.5" />
              {subPhase === 'playing' ? 'Playing...' : 'Hear question'}
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onclick={() => { showModelAnswer = !showModelAnswer; }}
              disabled={subPhase === 'recording'}
            >
              {showModelAnswer ? 'Hide model answer' : 'Show model answer'}
            </Button>
          </div>

          <!-- Model answer with listen counter + sentence drill -->
          {#if showModelAnswer}
            <div class="rounded-lg bg-muted/60 border p-4 space-y-3">
              <div class="flex items-center justify-between flex-wrap gap-2">
                <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Model Answer</p>
                <div class="flex items-center gap-2">
                  <!-- Listen count badge -->
                  {#if (modelAnswerListenCount[currentIdx] ?? 0) > 0}
                    <span class="text-[10px] font-bold px-1.5 py-0.5 rounded
                      {(modelAnswerListenCount[currentIdx] ?? 0) >= MAX_FREE_PLAYS
                        ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                        : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'}">
                      {(modelAnswerListenCount[currentIdx] ?? 0) >= MAX_FREE_PLAYS ? '📦 cached' : `🔊 ×${modelAnswerListenCount[currentIdx] ?? 0}`}
                    </span>
                  {/if}
                  <Button
                    variant="ghost"
                    size="sm"
                    onclick={playModelAnswer}
                    disabled={subPhase === 'playing' || subPhase === 'recording'}
                    class="h-7 text-xs"
                  >
                    <Play class="w-3 h-3 mr-1" />
                    {(modelAnswerListenCount[currentIdx] ?? 0) === 0 ? 'Listen' :
                     (modelAnswerListenCount[currentIdx] ?? 0) < MAX_FREE_PLAYS ? 'Listen again' :
                     'Play (from cache)'}
                  </Button>
                </div>
              </div>

              <!-- Answer text — each sentence clickable for drill -->
              <div class="text-sm leading-relaxed space-y-1">
                {#each splitSentences(currentQ.model_answer) as sentence}
                  <span
                    class="inline cursor-pointer hover:bg-primary/10 hover:text-primary rounded px-0.5 transition-colors"
                    title="Click to drill this sentence"
                    onclick={() => openDrill(sentence)}
                  >{sentence} </span>
                {/each}
              </div>
              <p class="text-[10px] text-muted-foreground">💡 Click any sentence to practice saying it</p>

              {#if currentQ.key_points?.length}
                <div class="space-y-1 pt-1 border-t border-border/50">
                  <p class="text-xs font-medium text-muted-foreground">Key points to hit:</p>
                  <ul class="space-y-0.5">
                    {#each currentQ.key_points as kp}
                      <li class="text-xs text-muted-foreground flex items-start gap-1.5">
                        <CircleCheck class="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary" />
                        {kp}
                      </li>
                    {/each}
                  </ul>
                </div>
              {/if}
            </div>
          {/if}
        </CardContent>
      </Card>


      <!-- Recording / transcription area -->
      {#if subPhase !== 'evaluated'}
        <Card>
          <CardContent class="pt-6 space-y-4">
            <div class="flex items-center justify-between">
              <p class="text-sm font-medium text-muted-foreground">Your Answer</p>
              {#if userRecordingLoaded.has(currentIdx)}
                <button
                  onclick={playUserRecording}
                  class="flex items-center gap-1.5 text-xs text-primary hover:underline"
                  title="Play back your recorded answer"
                >
                  <Play class="w-3.5 h-3.5" /> Play my recording
                </button>
              {/if}
            </div>

            <div class="flex gap-2 items-center">
              {#if subPhase === 'recording'}
                <Button onclick={stopRecording} variant="destructive" size="sm">
                  <Square class="w-3.5 h-3.5 mr-1.5" />
                  Stop ({recordLabel})
                </Button>
                <span class="flex items-center gap-1.5 text-xs text-red-500 animate-pulse">
                  <span class="w-2 h-2 rounded-full bg-red-500 inline-block"></span>
                  Recording...
                </span>
              {:else if subPhase === 'transcribing'}
                <Button disabled size="sm" variant="outline">
                  <div class="w-3.5 h-3.5 mr-1.5 border border-current border-t-transparent rounded-full animate-spin"></div>
                  Transcribing...
                </Button>
              {:else}
                <Button
                  onclick={startRecording}
                  variant="outline"
                  size="sm"
                  disabled={subPhase === 'playing' || subPhase === 'evaluating'}
                >
                  <Mic class="w-3.5 h-3.5 mr-1.5" />
                  {transcription ? 'Re-record' : 'Record answer'}
                </Button>
              {/if}
            </div>

            <Textarea
              placeholder="Your transcribed answer will appear here — you can also type directly."
              bind:value={transcription}
              rows={5}
              disabled={subPhase === 'recording' || subPhase === 'transcribing'}
            />

            <div class="flex gap-2">
              <Button
                onclick={handleEvaluate}
                disabled={!transcription.trim() || subPhase !== 'idle'}
                class="flex-1"
              >
                {subPhase === 'evaluating' ? 'Evaluating...' : 'Submit for evaluation'}
              </Button>
              <Button variant="outline" onclick={nextQuestion}>
                Skip <ChevronRight class="w-4 h-4 ml-1" />
              </Button>
            </div>
          </CardContent>
        </Card>
      {/if}

      <!-- Evaluation results -->
      {#if subPhase === 'evaluated' && evaluation}
        <Card class="border-2 {scoreBg(evaluation.score)}">
          <CardContent class="pt-6 space-y-5">
            <div class="flex items-center gap-4">
              <div class="text-5xl font-bold {scoreColor(evaluation.score)}">{evaluation.score}</div>
              <div>
                <p class="text-xs text-muted-foreground uppercase tracking-wide">Score</p>
                <p class="text-sm leading-relaxed mt-1">{evaluation.feedback}</p>
              </div>
              <!-- Play your recording from results view -->
              {#if userRecordingLoaded.has(currentIdx)}
                <button
                  onclick={playUserRecording}
                  class="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors shrink-0"
                  title="Replay your answer"
                >
                  <Play class="w-3.5 h-3.5" /> My answer
                </button>
              {/if}
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {#if evaluation.strengths?.length}
                <div class="space-y-1.5">
                  <p class="text-xs font-semibold text-green-700 dark:text-green-400 uppercase tracking-wide">Strengths</p>
                  <ul class="space-y-0.5">
                    {#each evaluation.strengths as s}
                      <li class="text-xs flex items-start gap-1.5">
                        <CircleCheck class="w-3.5 h-3.5 mt-0.5 shrink-0 text-green-600" />
                        {s}
                      </li>
                    {/each}
                  </ul>
                </div>
              {/if}

              {#if evaluation.areas_to_improve?.length}
                <div class="space-y-1.5">
                  <p class="text-xs font-semibold text-yellow-700 dark:text-yellow-400 uppercase tracking-wide">Improve</p>
                  <ul class="space-y-0.5">
                    {#each evaluation.areas_to_improve as a}
                      <li class="text-xs flex items-start gap-1.5">
                        <MicOff class="w-3.5 h-3.5 mt-0.5 shrink-0 text-yellow-600" />
                        {a}
                      </li>
                    {/each}
                  </ul>
                </div>
              {/if}
            </div>

            {#if evaluation.grammar_errors?.length}
              <div class="space-y-1.5">
                <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Language Notes</p>
                <ul class="space-y-0.5">
                  {#each evaluation.grammar_errors as g}
                    <li class="text-xs text-muted-foreground">• {g}</li>
                  {/each}
                </ul>
              </div>
            {/if}

            {#if evaluation.improved_answer}
              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Improved Answer</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    class="h-7 text-xs"
                    onclick={() => playTTS(evaluation!.improved_answer, 0.88)}
                    disabled={subPhase === 'playing'}
                  >
                    <Play class="w-3 h-3 mr-1" /> Listen
                  </Button>
                </div>
                <p class="text-sm leading-relaxed bg-background/60 rounded-lg p-3 border">{evaluation.improved_answer}</p>
              </div>
            {/if}

            <!-- ── Sentence Practice section ─────────────────────────────── -->
            {#if drillableSentences.length > 0}
              <div class="border-t border-border pt-4 space-y-3">
                <div>
                  <p class="text-xs font-bold uppercase tracking-wide text-primary">Sentence Practice</p>
                  <p class="text-[11px] text-muted-foreground mt-0.5">
                    Practice saying each sentence of the improved answer. Click Listen to hear it, then Record to say it back.
                  </p>
                </div>
                <div class="space-y-2">
                  {#each drillableSentences as sentence, i}
                    <div class="flex items-start gap-2 p-2.5 rounded-lg border border-border bg-background/50 hover:bg-muted/40 transition-colors">
                      <span class="shrink-0 w-5 h-5 rounded-full bg-muted text-muted-foreground text-[10px] font-bold flex items-center justify-center mt-0.5">{i + 1}</span>
                      <p class="flex-1 text-xs leading-relaxed">{sentence}</p>
                      <button
                        onclick={() => openDrill(sentence)}
                        class="shrink-0 flex items-center gap-1 text-[10px] font-semibold text-primary hover:bg-primary/10 px-2 py-1 rounded-md transition-colors"
                      >
                        <Mic class="w-3 h-3" /> Drill
                      </button>
                    </div>
                  {/each}
                </div>
                <p class="text-[10px] text-muted-foreground">
                  💡 {language === 'FR' ? 'Écoutez 2-3 fois avant d\'enregistrer.' : 'Listen 2-3 times before recording. Audio is cached — no extra cost.'}
                </p>
              </div>
            {/if}

            <Button onclick={nextQuestion} class="w-full">
              {currentIdx + 1 < questions.length ? 'Next Question' : 'Finish Session'}
              <ChevronRight class="w-4 h-4 ml-1" />
            </Button>
          </CardContent>
        </Card>
      {/if}
    </div>

  {:else if phase === 'done'}
    {@const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null}
    <div class="max-w-2xl mx-auto text-center space-y-6 py-12">
      <div class="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mx-auto">
        <CircleCheck class="w-8 h-8 text-green-600 dark:text-green-400" />
      </div>
      <div>
        <h2 class="text-2xl font-bold">Session Complete</h2>
        <p class="text-muted-foreground mt-2">You answered {questions.length} question{questions.length !== 1 ? 's' : ''}. Great work!</p>
        {#if avgScore !== null}
          <p class="mt-3 text-4xl font-bold {scoreColor(avgScore)}">{avgScore}<span class="text-lg font-normal text-muted-foreground">/100</span></p>
          <p class="text-xs text-muted-foreground mt-1">Average score across {scores.length} evaluated answer{scores.length !== 1 ? 's' : ''}</p>
        {/if}
      </div>
      <div class="flex gap-3 justify-center flex-wrap">
        <Button variant="outline" onclick={reset}>
          <RefreshCw class="w-4 h-4 mr-2" />
          New Session
        </Button>
        <Button onclick={() => { const jd = jobDescription; reset(); jobDescription = jd; }}>
          Same Job, New Questions
        </Button>
        <a href="/interview/sessions" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-colors text-muted-foreground">
          <History class="w-4 h-4" />
          View Session History
        </a>
      </div>
      {#if sessionId}
        <p class="text-xs text-muted-foreground">
          <a href="/interview/sessions/{sessionId}" class="text-primary hover:underline">View full session report →</a>
        </p>
      {/if}
    </div>
  {/if}
{/if}

<!-- ── Sentence Drill modal (fixed overlay, visible regardless of scroll) ── -->
{#if drillSentence}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    onclick={closeDrill}
  >
    <div
      class="w-full max-w-lg rounded-xl border-2 border-primary/30 bg-card shadow-2xl"
      onclick={(e) => e.stopPropagation()}
    >
      <div class="p-5 space-y-4">
        <div class="flex items-center justify-between">
          <p class="text-xs font-bold uppercase tracking-wide text-primary">Sentence Drill</p>
          <button onclick={closeDrill} class="text-muted-foreground hover:text-foreground">
            <X class="w-4 h-4" />
          </button>
        </div>

        <!-- Target sentence -->
        <div class="rounded-lg bg-muted/50 border p-3">
          <p class="text-xs text-muted-foreground mb-1 font-medium">Say this:</p>
          <p class="text-sm font-medium leading-relaxed">{drillSentence}</p>
        </div>

        <!-- Controls -->
        <div class="flex gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onclick={playDrillSentence}
            disabled={drillPhase === 'listening' || drillPhase === 'recording'}
          >
            <Volume2 class="w-3.5 h-3.5 mr-1.5" />
            {drillPhase === 'listening' ? 'Playing...' : 'Hear it'}
          </Button>

          {#if drillPhase === 'recording'}
            <Button variant="destructive" size="sm" onclick={stopDrillRecording}>
              <Square class="w-3.5 h-3.5 mr-1.5" />
              Stop ({drillRecordLabel})
            </Button>
            <span class="flex items-center gap-1.5 text-xs text-red-500 animate-pulse">
              <span class="w-2 h-2 rounded-full bg-red-500"></span> Recording
            </span>
          {:else if drillPhase === 'transcribing'}
            <Button disabled size="sm" variant="outline">
              <div class="w-3.5 h-3.5 mr-1.5 border border-current border-t-transparent rounded-full animate-spin"></div>
              Checking...
            </Button>
          {:else}
            <Button
              variant="outline"
              size="sm"
              onclick={startDrillRecording}
              disabled={drillPhase === 'listening'}
            >
              <Mic class="w-3.5 h-3.5 mr-1.5" />
              {drillPhase === 'result' ? 'Try again' : 'Say it'}
            </Button>
          {/if}
        </div>

        <!-- Result -->
        {#if drillPhase === 'result'}
          <div class="space-y-2">
            <div class="flex items-center gap-2">
              {#if drillMatch}
                <CheckCircle class="w-4 h-4 text-green-500 shrink-0" />
                <span class="text-sm font-semibold text-green-700 dark:text-green-400">Good match!</span>
              {:else}
                <RotateCcw class="w-4 h-4 text-yellow-500 shrink-0" />
                <span class="text-sm font-semibold text-yellow-700 dark:text-yellow-400">Try again</span>
              {/if}
            </div>
            {#if drillTranscription}
              <div class="text-xs bg-muted/50 border rounded-lg p-2.5 space-y-1">
                <p class="text-muted-foreground font-medium">You said:</p>
                <p class="leading-relaxed">{drillTranscription}</p>
              </div>
            {/if}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}
