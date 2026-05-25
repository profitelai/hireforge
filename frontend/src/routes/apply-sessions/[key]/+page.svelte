<script lang="ts">
  import { page } from '$app/state';
  import { getApplySession } from '$lib/api';
  import { toastState } from '$lib/toast.svelte';
  import type { ApplySession } from '$lib/types';
  import {
    ArrowLeft,
    BookOpen,
    Building2,
    CheckCircle2,
    ChevronDown,
    Circle,
    Clock,
    Copy,
    ExternalLink,
    FileText,
    Loader2,
    MapPin,
    TriangleAlert,
    Zap,
  } from '@lucide/svelte';

  let session = $state<ApplySession | null>(null);
  let loading = $state(true);
  let copied = $state(false);
  let jdExpanded = $state(false);

  const key = $derived(page.params.key);

  $effect(() => {
    if (key) loadSession();
  });

  async function loadSession() {
    loading = true;
    try {
      session = await getApplySession(key);
    } catch {
      toastState.error('Session not found.');
    } finally {
      loading = false;
    }
  }

  function copyUrl() {
    navigator.clipboard.writeText(window.location.href).then(() => {
      copied = true;
      setTimeout(() => { copied = false; }, 2000);
    });
  }

  const STATUS_STYLES: Record<string, string> = {
    completed:   'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300 border-green-200 dark:border-green-800',
    in_progress: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800',
    partial:     'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800',
    abandoned:   'bg-muted text-muted-foreground border-border',
  };

  const STATUS_LABELS: Record<string, string> = {
    completed:   'Completed',
    in_progress: 'In progress',
    partial:     'Partial',
    abandoned:   'Abandoned',
  };

  const APP_STATUS_STYLES: Record<string, string> = {
    applied:      'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    interviewing: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
    offer:        'bg-green-100 text-green-700',
    rejected:     'bg-muted text-muted-foreground',
  };

  function scoreColor(score: number | null) {
    if (!score) return 'text-muted-foreground';
    if (score >= 75) return 'text-green-600 dark:text-green-400';
    if (score >= 50) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-500 dark:text-red-400';
  }

  function formatDate(iso: string | null | undefined) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  const fit = $derived(session?.fit_analysis ?? null);
  const cfg = $derived(session?.config as Record<string, unknown> | null ?? null);

  // Determine what actions were completed
  const actionsDone = $derived(() => {
    if (!session) return [];
    const actions: { label: string; done: boolean; detail?: string }[] = [];
    actions.push({ label: 'Job analyzed & scraped', done: !!session.job_description });
    actions.push({
      label: 'Fit score calculated',
      done: session.match_score !== null,
      detail: session.match_score !== null ? `${session.match_score}/100` : undefined,
    });
    actions.push({ label: 'Application created', done: !!session.application_id });
    if (cfg?.generateCv) {
      actions.push({
        label: 'CV generated',
        done: session.status === 'completed',
        detail: cfg?.language === 'fr' ? 'French' : 'English',
      });
    }
    if (cfg?.generateCl) {
      actions.push({
        label: 'Cover letter generated',
        done: session.status === 'completed',
        detail: cfg?.tone ? String(cfg.tone) : undefined,
      });
    }
    return actions;
  });
</script>

<div class="max-w-2xl space-y-6 pb-20">
  <!-- Back + header -->
  <div class="flex items-center gap-3">
    <a href="/apply-sessions" class="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
      <ArrowLeft class="w-4 h-4" />
      All sessions
    </a>
  </div>

  {#if loading}
    <div class="space-y-4">
      {#each [1,2,3] as _}
        <div class="rounded-xl border border-border bg-card h-24 animate-pulse"></div>
      {/each}
    </div>
  {:else if !session}
    <div class="flex flex-col items-center justify-center py-20 gap-3 text-center">
      <TriangleAlert class="w-10 h-10 text-muted-foreground/40" />
      <p class="text-sm font-medium text-muted-foreground">Session not found</p>
      <a href="/apply-sessions" class="text-xs text-primary underline">Back to sessions</a>
    </div>
  {:else}
    <!-- Title row -->
    <div class="flex items-start gap-3">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <h1 class="text-xl font-bold truncate">
            {session.role_title || 'Unknown Role'}{session.company_name ? ` @ ${session.company_name}` : ''}
          </h1>
          <span class="text-xs font-semibold px-2 py-0.5 rounded-full border {STATUS_STYLES[session.status] ?? 'bg-muted text-muted-foreground border-border'}">
            {STATUS_LABELS[session.status] ?? session.status}
          </span>
        </div>
        <p class="text-xs text-muted-foreground mt-1">
          Session · <span class="font-mono">{key}</span> · {formatDate(session.created_at)}
        </p>
      </div>
      <button
        onclick={copyUrl}
        class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium hover:bg-accent transition-colors"
      >
        <Copy class="w-3 h-3" />
        {copied ? 'Copied!' : 'Copy URL'}
      </button>
    </div>

    <!-- Score + job info -->
    <div class="rounded-xl border border-border bg-card p-5 space-y-4">
      <div class="flex items-center gap-4">
        <!-- Score ring -->
        <div class="w-16 h-16 rounded-full border-2 flex flex-col items-center justify-center shrink-0
          {session.match_score !== null
            ? session.match_score >= 75 ? 'border-green-400' : session.match_score >= 50 ? 'border-yellow-400' : 'border-red-400'
            : 'border-border'}">
          {#if session.match_score !== null}
            <span class="text-xl font-bold {scoreColor(session.match_score)}">{session.match_score}</span>
            <span class="text-[9px] text-muted-foreground leading-none">/ 100</span>
          {:else}
            <Circle class="w-6 h-6 text-muted-foreground/40" />
          {/if}
        </div>

        <div class="flex-1 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          {#if session.company_name}
            <div class="flex items-center gap-1.5 text-muted-foreground text-xs">
              <Building2 class="w-3 h-3 shrink-0" />
              {session.company_name}
            </div>
          {/if}
          {#if session.location}
            <div class="flex items-center gap-1.5 text-muted-foreground text-xs">
              <MapPin class="w-3 h-3 shrink-0" />
              {session.location}
            </div>
          {/if}
          {#if session.salary}
            <div class="text-xs text-muted-foreground col-span-2">{session.salary}</div>
          {/if}
          {#if session.job_url}
            <a href={session.job_url} target="_blank" rel="noopener" class="flex items-center gap-1 text-xs text-primary hover:underline col-span-2">
              <ExternalLink class="w-3 h-3" />
              View original job posting
            </a>
          {/if}
        </div>
      </div>

      <!-- Job description (collapsible) -->
      {#if session.job_description}
        <div class="border-t border-border/50 pt-3">
          <button
            onclick={() => jdExpanded = !jdExpanded}
            class="flex items-center justify-between w-full text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <span>Job Description</span>
            <ChevronDown class="w-3.5 h-3.5 transition-transform {jdExpanded ? 'rotate-180' : ''}" />
          </button>
          {#if jdExpanded}
            <div class="mt-2 text-xs text-muted-foreground bg-muted/50 rounded-lg p-3 max-h-48 overflow-y-auto whitespace-pre-wrap">
              {session.job_description}
            </div>
          {:else}
            <p class="mt-1 text-xs text-muted-foreground truncate">{session.job_description.slice(0, 120)}…</p>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Actions completed -->
    <div class="rounded-xl border border-border bg-card p-5 space-y-3">
      <h2 class="text-sm font-semibold">What was done</h2>
      <div class="space-y-2">
        {#each actionsDone() as action}
          <div class="flex items-center gap-3">
            {#if action.done}
              <CheckCircle2 class="w-4 h-4 text-green-500 shrink-0" />
            {:else}
              <Circle class="w-4 h-4 text-muted-foreground/40 shrink-0" />
            {/if}
            <span class="text-sm {action.done ? 'text-foreground' : 'text-muted-foreground'}">{action.label}</span>
            {#if action.detail}
              <span class="ml-auto text-xs text-muted-foreground font-mono">{action.detail}</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <!-- Fit analysis -->
    {#if fit}
      <div class="rounded-xl border border-border bg-card p-5 space-y-4">
        <h2 class="text-sm font-semibold">Fit Analysis</h2>

        {#if fit.pros?.length}
          <div class="space-y-1.5">
            <p class="text-xs font-semibold text-green-600 dark:text-green-400 uppercase tracking-wide">Strengths</p>
            <ul class="space-y-1">
              {#each fit.pros as pro}
                <li class="text-xs text-muted-foreground flex items-start gap-2">
                  <span class="text-green-500 mt-0.5 shrink-0">+</span>{pro}
                </li>
              {/each}
            </ul>
          </div>
        {/if}

        {#if fit.cons?.length}
          <div class="space-y-1.5">
            <p class="text-xs font-semibold text-yellow-600 dark:text-yellow-400 uppercase tracking-wide">Gaps</p>
            <ul class="space-y-1">
              {#each fit.cons as con}
                <li class="text-xs text-muted-foreground flex items-start gap-2">
                  <span class="text-yellow-500 mt-0.5 shrink-0">−</span>{con}
                </li>
              {/each}
            </ul>
          </div>
        {/if}

        {#if fit.missing_keywords?.length}
          <div class="space-y-1.5">
            <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Missing keywords</p>
            <div class="flex flex-wrap gap-1.5">
              {#each fit.missing_keywords as kw}
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground border border-border">{kw}</span>
              {/each}
            </div>
          </div>
        {/if}

        {#if fit.red_flags?.length}
          <div class="space-y-1.5">
            <p class="text-xs font-semibold text-red-500 uppercase tracking-wide">Red flags</p>
            <ul class="space-y-1">
              {#each fit.red_flags as flag}
                <li class="text-xs text-muted-foreground flex items-start gap-2">
                  <span class="text-red-400 mt-0.5 shrink-0">!</span>{flag}
                </li>
              {/each}
            </ul>
          </div>
        {/if}
      </div>
    {/if}

    <!-- Application + generated docs -->
    {#if session.application}
      {@const app = session.application}
      <div class="rounded-xl border border-border bg-card p-5 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold">Application</h2>
          <a href="/pipeline/{app.id}" class="flex items-center gap-1.5 text-xs text-primary hover:underline">
            <ExternalLink class="w-3 h-3" />
            Open pipeline
          </a>
        </div>

        <div class="flex items-center gap-3">
          <span class="text-xs px-2 py-0.5 rounded-full font-medium capitalize {APP_STATUS_STYLES[app.status] ?? 'bg-muted text-muted-foreground'}">
            {app.status}
          </span>
          {#if app.applied_date}
            <span class="text-xs text-muted-foreground">Applied {app.applied_date}</span>
          {/if}
        </div>

        <!-- Generated CV -->
        {#if session.generated_cv}
          {@const cv = session.generated_cv}
          <div class="rounded-lg border border-border bg-muted/30 p-3 flex items-center gap-3">
            <FileText class="w-4 h-4 text-primary shrink-0" />
            <div class="flex-1 min-w-0">
              <p class="text-xs font-semibold">Resume / CV</p>
              <p class="text-[10px] text-muted-foreground mt-0.5">
                {cv.enhanced ? 'ATS-enhanced' : 'Standard'} ·
                {cv.language === 'fr' ? '🇫🇷 French' : '🇬🇧 English'}
                {#if cv.match_score !== null} · Score after: {cv.match_score}{/if}
                · {formatDate(cv.created_at)}
              </p>
            </div>
            <a href="/history?type=cv&app={app.id}" class="shrink-0 text-xs text-primary hover:underline">View</a>
          </div>
        {/if}

        <!-- Generated CL -->
        {#if session.generated_cl}
          {@const cl = session.generated_cl}
          <div class="rounded-lg border border-border bg-muted/30 p-3 space-y-2">
            <div class="flex items-center gap-3">
              <FileText class="w-4 h-4 text-primary shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="text-xs font-semibold">Cover Letter</p>
                <p class="text-[10px] text-muted-foreground mt-0.5">
                  Tone: {cl.tone} ·
                  {cl.language === 'fr' ? '🇫🇷 French' : '🇬🇧 English'}
                  · {formatDate(cl.created_at)}
                </p>
              </div>
              <a href="/history?type=cl&app={app.id}" class="shrink-0 text-xs text-primary hover:underline">View</a>
            </div>
            {#if cl.cover_letter_text}
              <p class="text-xs text-muted-foreground bg-background rounded p-2 border border-border line-clamp-3 leading-relaxed">
                {cl.cover_letter_text}
              </p>
            {/if}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Config used -->
    {#if cfg}
      <div class="rounded-xl border border-border bg-card p-5 space-y-3">
        <h2 class="text-sm font-semibold">Session configuration</h2>
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div class="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/50">
            <span class="text-muted-foreground">Language</span>
            <span class="font-medium">{cfg.language === 'fr' ? '🇫🇷 French' : '🇬🇧 English'}</span>
          </div>
          {#if cfg.tone}
            <div class="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/50">
              <span class="text-muted-foreground">CL tone</span>
              <span class="font-medium capitalize">{cfg.tone}</span>
            </div>
          {/if}
          <div class="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/50">
            <span class="text-muted-foreground">ATS enhance</span>
            <span class="font-medium">{cfg.cvEnhance ? 'Yes' : 'No'}</span>
          </div>
          <div class="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/50">
            <span class="text-muted-foreground">Generated</span>
            <span class="font-medium">
              {[cfg.generateCv && 'CV', cfg.generateCl && 'CL'].filter(Boolean).join(' + ') || '—'}
            </span>
          </div>
        </div>
      </div>
    {/if}
  {/if}
</div>
