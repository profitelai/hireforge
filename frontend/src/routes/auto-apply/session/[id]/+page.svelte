<script lang="ts">
  import { page } from '$app/state';
  import { activeProfile } from '$lib/activeProfile.svelte';
  import {
    applyToJob,
    enrichJob,
    generateClForJob,
    generateCvForJob,
    generateCvPdf,
    getCoverLetterHistoryEntry,
    getCvHistoryEntry,
    generateCoverLetterPdf,
    listAutoApplyResults,
    listAutoApplySessions,
    listJobCvVersions,
    scoreJob,
    updateJobResultStatus,
    type AutoApplySessionEntry,
    type JobSearchResultEntry,
  } from '$lib/api';
  import { toastState as toast } from '$lib/toast.svelte';
  import { pdfFilename as buildPdfFilename } from '$lib/utils';
  import {
    AlertCircle,
    ArrowLeft,
    Bot,
    Briefcase,
    CheckCircle,
    ChevronDown,
    ChevronUp,
    Clock,
    Download,
    ExternalLink,
    FileText,
    History,
    Loader2,
    MapPin,
    RefreshCw,
    SkipForward,
    Sparkles,
  } from '@lucide/svelte';

  // ── Session ───────────────────────────────────────────────────────────────
  const sessionId = $derived(page.params.id);
  let session = $state<AutoApplySessionEntry | null>(null);

  async function loadSession() {
    const ap = activeProfile.current;
    try {
      const res = await listAutoApplySessions({ profile_id: ap?.id });
      session = res.items.find(s => s.session_id === sessionId) ?? null;
    } catch {}
  }

  // ── Jobs ──────────────────────────────────────────────────────────────────
  let results       = $state<JobSearchResultEntry[]>([]);
  let loading       = $state(false);
  let expandedIds   = $state<Set<number>>(new Set());

  // Per-job in-progress sets
  let enrichingIds    = $state<Set<number>>(new Set());
  let scoringIds      = $state<Set<number>>(new Set());
  let generatingCvIds = $state<Set<number>>(new Set());
  let regenCvIds      = $state<Set<number>>(new Set());
  let generatingClIds = $state<Set<number>>(new Set());
  let applyingIds     = $state<Set<number>>(new Set());
  let downloadingIds  = $state<Set<number>>(new Set());

  // CV versions per job
  let cvVersionsMap = $state<Record<number, { id: number; created_at: string; enhanced: boolean; match_score: number | null }[]>>({});

  // Run-all
  let runningAll    = $state(false);
  let runAllProgress = $state(0);
  let runAllTotal   = $state(0);

  // ── Derived ───────────────────────────────────────────────────────────────
  function jobStage(j: JobSearchResultEntry): 0 | 1 | 2 | 3 | 4 {
    if (j.status === 'applied') return 4;
    if (j.cl_id)    return 3;
    if (j.cv_id)    return 2;
    if (j.match_score !== null) return 1;
    return 0;
  }

  function scoreColor(score: number | null) {
    if (score === null) return 'text-muted-foreground';
    if (score >= 80) return 'text-emerald-600 dark:text-emerald-400';
    if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-500 dark:text-red-400';
  }

  const activeResults   = $derived(results.filter(r => r.status !== 'cl_ready' && r.status !== 'applied' && !r.cl_id));
  const failedResults   = $derived(results.filter(r => r.status === 'failed'));
  const needsWork       = $derived(activeResults.filter(r => jobStage(r) < 3 && r.status !== 'skipped' && r.status !== 'failed'));
  const scoredCount     = $derived(results.filter(r => r.match_score !== null).length);
  const cvCount         = $derived(results.filter(r => r.cv_id !== null).length);
  const clCount         = $derived(results.filter(r => r.cl_id !== null).length);
  const appliedCount    = $derived(results.filter(r => r.status === 'applied').length);
  const completedCount  = $derived(results.filter(r => r.status === 'cl_ready' || r.status === 'applied' || r.cl_id).length);
  const failedCount     = $derived(failedResults.length);

  // ── Load ──────────────────────────────────────────────────────────────────
  async function loadResults() {
    loading = true;
    try {
      const res = await listAutoApplyResults(undefined, undefined, sessionId);
      results = res.items;
    } catch (e: any) {
      toast.error(e.message ?? 'Failed to load jobs.');
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (sessionId) {
      loadSession();
      loadResults().then(() => {
        const pending = results.filter(r => !r.description && r.status === 'pending');
        for (const job of pending) doEnrich(job);
      });
    }
  });

  // ── Pipeline actions ──────────────────────────────────────────────────────
  async function doEnrich(job: JobSearchResultEntry): Promise<JobSearchResultEntry> {
    enrichingIds = new Set([...enrichingIds, job.id]);
    try {
      const updated = await enrichJob(job.id);
      results = results.map(r => r.id === job.id ? updated : r);
      return updated;
    } catch { return job; }
    finally {
      enrichingIds.delete(job.id);
      enrichingIds = new Set(enrichingIds);
    }
  }

  async function doScore(job: JobSearchResultEntry): Promise<JobSearchResultEntry> {
    scoringIds = new Set([...scoringIds, job.id]);
    try {
      const updated = await scoreJob(job.id);
      results = results.map(r => r.id === job.id ? updated : r);
      return updated;
    } finally {
      scoringIds.delete(job.id);
      scoringIds = new Set(scoringIds);
    }
  }

  async function doGenerateCv(job: JobSearchResultEntry): Promise<JobSearchResultEntry> {
    generatingCvIds = new Set([...generatingCvIds, job.id]);
    try {
      const updated = await generateCvForJob(job.id);
      results = results.map(r => r.id === job.id ? updated : r);
      // Refresh CV versions for this job
      loadCvVersions(job.id);
      return updated;
    } finally {
      generatingCvIds.delete(job.id);
      generatingCvIds = new Set(generatingCvIds);
    }
  }

  async function doRegenCv(job: JobSearchResultEntry) {
    regenCvIds = new Set([...regenCvIds, job.id]);
    try {
      const updated = await generateCvForJob(job.id);
      results = results.map(r => r.id === job.id ? updated : r);
      await loadCvVersions(job.id);
      toast.success('New resume version created with missing keywords.');
    } catch (e: any) {
      toast.error(`Regeneration failed: ${e.message}`);
    } finally {
      regenCvIds.delete(job.id);
      regenCvIds = new Set(regenCvIds);
    }
  }

  async function doGenerateCl(job: JobSearchResultEntry): Promise<JobSearchResultEntry> {
    generatingClIds = new Set([...generatingClIds, job.id]);
    try {
      const updated = await generateClForJob(job.id);
      results = results.map(r => r.id === job.id ? updated : r);
      return updated;
    } finally {
      generatingClIds.delete(job.id);
      generatingClIds = new Set(generatingClIds);
    }
  }

  async function doFullPipeline(job: JobSearchResultEntry) {
    try {
      let cur = job;
      if (!cur.description) cur = await doEnrich(cur);
      if (jobStage(cur) < 1) {
        cur = await doScore(cur);
        if (cur.status === 'failed') return;
      }
      if (jobStage(cur) < 2) {
        cur = await doGenerateCv(cur);
        if (cur.status === 'failed') return;
      }
      if (jobStage(cur) < 3) await doGenerateCl(cur);
    } catch (e: any) {
      results = results.map(r => r.id === job.id ? { ...r, status: 'failed', error_message: e.message } : r);
    }
  }

  async function handleRunAll() {
    if (needsWork.length === 0) return toast.error('All jobs are already done.');
    runningAll = true;
    runAllProgress = 0;
    runAllTotal = needsWork.length;
    for (const job of needsWork) {
      await doFullPipeline(job);
      runAllProgress += 1;
    }
    runningAll = false;
    toast.success(`Processed ${runAllTotal} jobs.`);
  }

  async function handleRetryAllFailed() {
    const failed = failedResults;
    if (failed.length === 0) return;
    runningAll = true;
    runAllProgress = 0;
    runAllTotal = failed.length;
    for (const job of failed) {
      // Reset to scored if it has a score, else full pipeline
      const updated = await updateJobResultStatus(job.id, 'pending');
      results = results.map(r => r.id === job.id ? { ...updated, match_score: r.match_score, match_data: r.match_data } : r);
      await doFullPipeline({ ...job, status: 'pending' });
      runAllProgress += 1;
    }
    runningAll = false;
    toast.success(`Retried ${runAllTotal} failed jobs.`);
  }

  async function handleSkip(id: number) {
    try {
      const u = await updateJobResultStatus(id, 'skipped');
      results = results.map(r => r.id === id ? u : r);
    } catch (e: any) { toast.error(e.message); }
  }

  async function handleApply(id: number) {
    const ap = activeProfile.current;
    if (!ap) return toast.error('Select a profile first.');
    applyingIds = new Set([...applyingIds, id]);
    try {
      const u = await applyToJob(id, ap.id);
      results = results.map(r => r.id === id ? u : r);
      if (u.status === 'applied') toast.success('Application submitted!');
      else toast.error(u.error_message ?? 'Apply failed — try manually.');
    } catch (e: any) { toast.error(e.message ?? 'Apply failed.'); }
    finally {
      applyingIds.delete(id);
      applyingIds = new Set(applyingIds);
    }
  }

  // ── CV versions ───────────────────────────────────────────────────────────
  async function loadCvVersions(jobId: number) {
    try {
      const res = await listJobCvVersions(jobId);
      cvVersionsMap = { ...cvVersionsMap, [jobId]: res.items };
    } catch {}
  }

  async function loadCvVersionsIfExpanded(jobId: number) {
    if (expandedIds.has(jobId) && !cvVersionsMap[jobId]) {
      loadCvVersions(jobId);
    }
  }

  function toggleExpand(id: number) {
    if (expandedIds.has(id)) expandedIds.delete(id);
    else {
      expandedIds.add(id);
      loadCvVersionsIfExpanded(id);
    }
    expandedIds = new Set(expandedIds);
  }

  // ── Downloads ─────────────────────────────────────────────────────────────
  async function downloadCv(job: JobSearchResultEntry, cvId?: number) {
    const id = cvId ?? job.cv_id;
    if (!id) return;
    downloadingIds = new Set([...downloadingIds, job.id]);
    try {
      const entry = await getCvHistoryEntry(id);
      const profile = JSON.parse(entry.profile_snapshot);
      const blob = await generateCvPdf({ profile });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = buildPdfFilename('resume', { position: job.role_title, company: job.company_name, name: activeProfile.current?.name });
      a.click();
    } catch (e: any) { toast.error(`Download failed: ${e.message}`); }
    finally {
      downloadingIds.delete(job.id);
      downloadingIds = new Set(downloadingIds);
    }
  }

  async function downloadCl(job: JobSearchResultEntry) {
    if (!job.cl_id) return;
    downloadingIds = new Set([...downloadingIds, job.id]);
    try {
      const entry = await getCoverLetterHistoryEntry(job.cl_id);
      let clProfile: any = null;
      if (job.cv_id) {
        try { const cv = await getCvHistoryEntry(job.cv_id); clProfile = JSON.parse(cv.profile_snapshot); } catch {}
      }
      const blob = await generateCoverLetterPdf({
        text: entry.cover_letter_text,
        name: clProfile?.name ?? activeProfile.current?.name,
        email: clProfile?.email, phone: clProfile?.phone, location: clProfile?.location,
        linkedin: clProfile?.linkedin, github: clProfile?.github, portfolio: clProfile?.portfolio,
      });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = buildPdfFilename('cover_letter', { position: job.role_title, company: job.company_name, name: activeProfile.current?.name });
      a.click();
    } catch (e: any) { toast.error(`Download failed: ${e.message}`); }
    finally {
      downloadingIds.delete(job.id);
      downloadingIds = new Set(downloadingIds);
    }
  }

  function parseMatchData(raw: string | null) {
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }
</script>

<div class="max-w-4xl mx-auto space-y-5">

  <!-- Header -->
  <div class="flex items-center gap-3">
    <a href="/auto-apply" class="p-1.5 rounded-lg hover:bg-accent transition-colors text-muted-foreground">
      <ArrowLeft class="w-5 h-5" />
    </a>
    <div class="p-2 rounded-lg bg-primary/10 shrink-0">
      <Bot class="w-5 h-5 text-primary" />
    </div>
    <div class="flex-1 min-w-0">
      <h1 class="text-xl font-bold truncate">{session?.label ?? sessionId}</h1>
      <div class="flex items-center gap-3 text-xs text-muted-foreground mt-0.5 flex-wrap">
        {#if session?.search_keyword}
          <span class="flex items-center gap-1"><Briefcase class="w-3 h-3" />{session.search_keyword}</span>
        {/if}
        {#if session?.location}
          <span class="flex items-center gap-1"><MapPin class="w-3 h-3" />{session.location}</span>
        {/if}
        {#if session?.created_at}
          <span class="flex items-center gap-1"><Clock class="w-3 h-3" />{formatDate(session.created_at)}</span>
        {/if}
      </div>
    </div>
    <div class="flex items-center gap-2 shrink-0">
      <a href="/history" class="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border hover:bg-accent transition-colors text-muted-foreground">
        <History class="w-3.5 h-3.5" /> History
      </a>
      <button onclick={loadResults} disabled={loading}
        class="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border hover:bg-accent transition-colors">
        <RefreshCw class={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
      </button>
    </div>
  </div>

  <!-- Stats -->
  <div class="grid grid-cols-6 gap-2 text-center">
    {#each [
      ['Total', results.length, ''],
      ['Scored', scoredCount, 'text-blue-600 dark:text-blue-400'],
      ['Resume', cvCount, 'text-purple-600 dark:text-purple-400'],
      ['Cover Letter', clCount, 'text-indigo-600 dark:text-indigo-400'],
      ['Applied', appliedCount, 'text-emerald-600 dark:text-emerald-400'],
      ['Failed', failedCount, 'text-red-500 dark:text-red-400'],
    ] as [label, count, cls]}
      <div class="rounded-lg border bg-card px-2 py-2.5">
        <div class={`text-lg font-black ${cls}`}>{count}</div>
        <div class="text-[10px] text-muted-foreground mt-0.5 leading-tight">{label}</div>
      </div>
    {/each}
  </div>

  <!-- Run-all banner -->
  {#if !runningAll && needsWork.length > 0}
    <div class="rounded-xl border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/20 p-4 flex items-center gap-4">
      <Sparkles class="w-7 h-7 text-purple-500 shrink-0" />
      <div class="flex-1 min-w-0">
        <p class="font-semibold text-sm">{needsWork.length} job{needsWork.length === 1 ? '' : 's'} ready to process</p>
        <p class="text-xs text-muted-foreground">Score → Tailored Resume → Cover Letter for all</p>
      </div>
      <button onclick={handleRunAll}
        class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium transition-colors">
        <Sparkles class="w-4 h-4" /> Run All
      </button>
    </div>
  {/if}

  <!-- Retry all failed banner -->
  {#if !runningAll && failedCount > 0}
    <div class="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4 flex items-center gap-4">
      <AlertCircle class="w-6 h-6 text-red-500 shrink-0" />
      <div class="flex-1 min-w-0">
        <p class="font-semibold text-sm text-red-700 dark:text-red-300">{failedCount} job{failedCount === 1 ? '' : 's'} failed</p>
        <p class="text-xs text-red-600/80 dark:text-red-400/80">Usually a timeout — retrying with the 270s timeout now set should work</p>
      </div>
      <button onclick={handleRetryAllFailed}
        class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium transition-colors">
        <RefreshCw class="w-4 h-4" /> Retry All Failed
      </button>
    </div>
  {/if}

  <!-- Progress -->
  {#if runningAll}
    <div class="rounded-xl border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/20 p-4 space-y-2">
      <div class="flex items-center gap-3">
        <Loader2 class="w-5 h-5 animate-spin text-purple-500" />
        <p class="text-sm font-medium">Running… {runAllProgress} / {runAllTotal}</p>
      </div>
      <div class="w-full bg-purple-200 dark:bg-purple-800 rounded-full h-1.5">
        <div class="bg-purple-600 h-1.5 rounded-full transition-all duration-300"
          style="width: {runAllTotal > 0 ? (runAllProgress / runAllTotal) * 100 : 0}%"></div>
      </div>
    </div>
  {/if}

  <!-- Completed notice -->
  {#if completedCount > 0}
    <div class="rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 px-4 py-2.5 flex items-center justify-between">
      <p class="text-xs text-emerald-700 dark:text-emerald-300">
        <span class="font-semibold">{completedCount} job{completedCount === 1 ? '' : 's'}</span> fully processed —
        <a href="/history" class="underline hover:no-underline font-medium">view in History</a>
      </p>
    </div>
  {/if}

  <!-- Jobs -->
  {#if loading && activeResults.length === 0}
    <div class="flex items-center justify-center py-16 text-muted-foreground">
      <Loader2 class="w-5 h-5 animate-spin mr-2" /> Loading jobs…
    </div>
  {:else if activeResults.length === 0}
    <div class="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
      <Bot class="w-10 h-10 opacity-30" />
      <p class="text-sm">{results.length > 0 ? 'All jobs done — check History.' : 'No jobs in this session.'}</p>
    </div>
  {:else}
    <div class="space-y-3">
      {#each activeResults as job (job.id)}
        {@const stage = jobStage(job)}
        {@const md = parseMatchData(job.match_data)}
        {@const isExpanded = expandedIds.has(job.id)}
        {@const isEnriching = enrichingIds.has(job.id)}
        {@const isScoring = scoringIds.has(job.id)}
        {@const isGenCv = generatingCvIds.has(job.id)}
        {@const isRegen = regenCvIds.has(job.id)}
        {@const isGenCl = generatingClIds.has(job.id)}
        {@const isApplying = applyingIds.has(job.id)}
        {@const isDl = downloadingIds.has(job.id)}
        {@const isBusy = isEnriching || isScoring || isGenCv || isRegen || isGenCl || isApplying}
        {@const isSkipped = job.status === 'skipped'}
        {@const isFailed = job.status === 'failed'}
        {@const cvVersions = cvVersionsMap[job.id] ?? []}

        <div class="rounded-xl border bg-card overflow-hidden {isSkipped ? 'opacity-50' : ''}">
          <div class="flex items-start gap-3 p-4">
            <!-- Score -->
            <div class="shrink-0 w-12 h-12 rounded-lg bg-muted flex flex-col items-center justify-center">
              {#if isScoring || isEnriching}
                <Loader2 class="w-4 h-4 animate-spin text-blue-500" />
              {:else if job.match_score !== null}
                <span class={`text-lg font-black leading-none ${scoreColor(job.match_score)}`}>{job.match_score}</span>
                <span class="text-[10px] text-muted-foreground">%</span>
              {:else if isFailed}
                <AlertCircle class="w-4 h-4 text-red-500" />
              {:else}
                <span class="text-[10px] text-muted-foreground text-center">—</span>
              {/if}
            </div>

            <!-- Job info -->
            <div class="flex-1 min-w-0">
              <div class="flex items-start gap-2">
                <div class="flex-1 min-w-0">
                  <p class="font-semibold text-sm leading-tight truncate">{job.role_title ?? 'Fetching…'}</p>
                  <p class="text-xs text-muted-foreground mt-0.5">
                    {job.company_name ?? '—'}
                    {#if job.location} · {job.location}{/if}
                    {#if job.salary} · {job.salary}{/if}
                    {#if job.easy_apply} · <span class="text-blue-600 dark:text-blue-400">Easy Apply</span>{/if}
                  </p>
                </div>
                {#if job.job_url}
                  <a href={job.job_url} target="_blank" rel="noopener noreferrer"
                    class="text-muted-foreground hover:text-foreground shrink-0">
                    <ExternalLink class="w-3.5 h-3.5" />
                  </a>
                {/if}
              </div>

              <!-- Pipeline dots -->
              <div class="flex items-center gap-1 mt-2.5">
                {#each [
                  { label: 'Score', done: stage >= 1, active: isScoring },
                  { label: 'Resume', done: stage >= 2, active: isGenCv },
                  { label: 'Cover Letter', done: stage >= 3, active: isGenCl },
                  { label: 'Applied', done: stage >= 4, active: isApplying },
                ] as s, i}
                  {#if i > 0}<div class="flex-1 h-px {stage > i ? 'bg-primary' : 'bg-border'}"></div>{/if}
                  <div class="flex flex-col items-center gap-0.5">
                    <div class={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] transition-colors ${
                      s.done ? 'bg-primary text-primary-foreground'
                      : s.active ? 'bg-blue-100 dark:bg-blue-900/40 border-2 border-blue-500'
                      : 'bg-muted border border-border'
                    }`}>
                      {#if s.active}<Loader2 class="w-2.5 h-2.5 animate-spin text-blue-500" />
                      {:else if s.done}✓
                      {:else}{i + 1}{/if}
                    </div>
                    <span class="text-[9px] text-muted-foreground whitespace-nowrap">{s.label}</span>
                  </div>
                {/each}
              </div>
            </div>
          </div>

          <!-- Action bar -->
          <div class="flex items-center gap-2 px-4 pb-3 flex-wrap">
            {#if stage < 3 && !isBusy && !isSkipped && !isFailed}
              <button onclick={() => doFullPipeline(job)}
                class="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-purple-300 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/20 transition-colors">
                <Sparkles class="w-3 h-3" />
                {stage === 0 ? 'Run Pipeline' : stage === 1 ? 'Resume + CL' : 'Cover Letter'}
              </button>
            {/if}
            {#if isFailed && !isBusy}
              <button onclick={() => doFullPipeline(job)}
                class="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-red-300 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                <RefreshCw class="w-3 h-3" /> Retry
              </button>
            {/if}
            {#if stage === 1 && !isBusy && !isSkipped}
              <button onclick={() => doGenerateCv(job)}
                class="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border hover:bg-accent transition-colors">
                <FileText class="w-3 h-3" /> Resume
              </button>
            {/if}
            {#if stage >= 1 && !isBusy && !isSkipped && md?.missing_keywords?.length}
              <button onclick={() => doRegenCv(job)} disabled={isRegen}
                class="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-yellow-400 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-50 dark:hover:bg-yellow-900/20 transition-colors disabled:opacity-50">
                {#if isRegen}<Loader2 class="w-3 h-3 animate-spin" />Generating…
                {:else}<RefreshCw class="w-3 h-3" />{job.cv_id ? 'Improve Resume' : 'Generate Resume'} <span class="opacity-60">({md.missing_keywords.length} keywords)</span>{/if}
              </button>
            {/if}
            {#if stage === 2 && !isBusy && !isSkipped}
              <button onclick={() => doGenerateCl(job)}
                class="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border hover:bg-accent transition-colors">
                <FileText class="w-3 h-3" /> Cover Letter
              </button>
            {/if}

            <!-- Downloads -->
            {#if job.cv_id}
              <button onclick={() => downloadCv(job)} disabled={isDl}
                class="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-purple-300 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/20 transition-colors disabled:opacity-50">
                {#if isDl}<Loader2 class="w-3 h-3 animate-spin" />{:else}<Download class="w-3 h-3" />{/if}
                Resume PDF {#if cvVersions.length > 1}<span class="text-[10px] opacity-70">v{cvVersions.length}</span>{/if}
              </button>
            {/if}
            {#if job.cl_id}
              <button onclick={() => downloadCl(job)} disabled={isDl}
                class="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-indigo-300 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors disabled:opacity-50">
                {#if isDl}<Loader2 class="w-3 h-3 animate-spin" />{:else}<Download class="w-3 h-3" />{/if}
                CL PDF
              </button>
            {/if}

            <!-- Apply -->
            {#if stage >= 3 && job.status !== 'applied' && !isSkipped}
              <button onclick={() => handleApply(job.id)} disabled={isApplying}
                class="flex items-center gap-1.5 text-xs px-3 py-1 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 font-medium">
                {#if isApplying}<Loader2 class="w-3 h-3 animate-spin" /> Applying…
                {:else}<CheckCircle class="w-3 h-3" /> Apply{/if}
              </button>
            {/if}
            {#if job.status === 'applied'}
              <span class="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                <CheckCircle class="w-3 h-3" /> Applied
              </span>
            {/if}

            <!-- Skip / restore -->
            {#if !isSkipped && stage < 4 && !isBusy}
              <button onclick={() => handleSkip(job.id)}
                class="ml-auto flex items-center gap-1 text-xs px-2 py-1 rounded text-muted-foreground hover:text-foreground">
                <SkipForward class="w-3 h-3" /> Skip
              </button>
            {:else if isSkipped}
              <button onclick={async () => { const u = await updateJobResultStatus(job.id, 'pending'); results = results.map(r => r.id === job.id ? u : r); }}
                class="ml-auto text-xs text-muted-foreground hover:text-foreground">Restore</button>
            {/if}

            {#if md || job.error_message}
              <button onclick={() => toggleExpand(job.id)}
                class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground {isSkipped ? '' : 'ml-1'}">
                {#if isExpanded}<ChevronUp class="w-3.5 h-3.5" />{:else}<ChevronDown class="w-3.5 h-3.5" />{/if}
              </button>
            {/if}
          </div>

          <!-- Expanded -->
          {#if isExpanded}
            <div class="border-t bg-muted/30 px-4 py-3 space-y-3">
              {#if job.error_message}
                <div class="flex items-start gap-2 text-red-600 dark:text-red-400">
                  <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
                  <p class="text-xs">{job.error_message}</p>
                </div>
              {/if}

              {#if md}
                <div class="grid sm:grid-cols-2 gap-3">
                  {#if md.pros?.length}
                    <div>
                      <p class="text-xs font-medium text-emerald-600 dark:text-emerald-400 mb-1">Strengths</p>
                      <ul class="space-y-0.5">{#each md.pros as p}<li class="text-xs text-muted-foreground">· {p}</li>{/each}</ul>
                    </div>
                  {/if}
                  {#if md.cons?.length}
                    <div>
                      <p class="text-xs font-medium text-red-500 mb-1">Gaps</p>
                      <ul class="space-y-0.5">{#each md.cons as c}<li class="text-xs text-muted-foreground">· {c}</li>{/each}</ul>
                    </div>
                  {/if}
                  {#if md.missing_keywords?.length}
                    <div class="sm:col-span-2 space-y-2">
                      <p class="text-xs font-medium text-yellow-600 dark:text-yellow-400">Missing keywords</p>
                      <div class="flex flex-wrap gap-1">
                        {#each md.missing_keywords as kw}
                          <span class="text-[11px] px-1.5 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300">{kw}</span>
                        {/each}
                      </div>
                      {#if job.cv_id}
                        <button onclick={() => doRegenCv(job)} disabled={isRegen || isBusy}
                          class="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-dashed border-yellow-400/70 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-50 dark:hover:bg-yellow-900/20 transition-colors disabled:opacity-50">
                          {#if isRegen}<Loader2 class="w-3 h-3 animate-spin" /> Generating new version…
                          {:else}<RefreshCw class="w-3 h-3" /> New resume version with these keywords{/if}
                        </button>
                      {/if}
                    </div>
                  {/if}
                  {#if md.suggested_emphasis}
                    <div class="sm:col-span-2">
                      <p class="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1">Suggested emphasis</p>
                      <p class="text-xs text-muted-foreground">{md.suggested_emphasis}</p>
                    </div>
                  {/if}
                </div>
              {/if}

              <!-- Resume versions -->
              {#if cvVersions.length > 1}
                <div>
                  <p class="text-xs font-medium text-muted-foreground mb-1.5">Resume versions ({cvVersions.length})</p>
                  <div class="flex flex-wrap gap-1.5">
                    {#each cvVersions as cv, i}
                      <button onclick={() => downloadCv(job, cv.id)}
                        class="flex items-center gap-1 text-[11px] px-2 py-1 rounded border hover:bg-accent transition-colors">
                        <Download class="w-3 h-3" />
                        v{cvVersions.length - i}
                        {#if cv.match_score !== null}
                          <span class={`font-semibold ${scoreColor(cv.match_score)}`}>{cv.match_score}%</span>
                        {/if}
                        <span class="text-muted-foreground text-[10px]">
                          {new Date(cv.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </button>
                    {/each}
                  </div>
                </div>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>
