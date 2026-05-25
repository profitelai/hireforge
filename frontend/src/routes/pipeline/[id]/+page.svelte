<script lang="ts">
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { activeProfile } from '$lib/activeProfile.svelte';
  import {
    getApplication,
    getCvHistoryEntry,
    getCoverLetterHistoryEntry,
    generateCoverLetterPdf,
    generateCvPdf,
    updateApplication,
    scrapeAnalyze,
    generateCvStream,
    generateCoverLetterStream,
    analyzeFitWithCv,
  } from '$lib/api';
  import { consumeStructuredStream } from '$lib/stream';
  import { toastState } from '$lib/toast.svelte';
  import { errorMessage, formatDate, formatDateShort, pdfFilename } from '$lib/utils';
  import { Button } from '$lib/components/ui/button';
  import { Card, CardContent } from '$lib/components/ui/card';
  import { Textarea } from '$lib/components/ui/textarea';
  import CvPreview from '$lib/components/CvPreview.svelte';
  import CoverLetterPreview from '$lib/components/CoverLetterPreview.svelte';
  import type { ApplicationEntry, FitAnalysisResponse, GeneratedCVEntry, GeneratedCoverLetterEntry, ProfileData } from '$lib/types';
  import {
    ArrowLeft,
    CheckCircle,
    ChevronDown,
    ChevronUp,
    CircleDashed,
    ClipboardList,
    Download,
    ExternalLink,
    FileText,
    Loader,
    Mic,
    RefreshCw,
    Search,
    Sparkles,
    TrendingUp,
    X,
  } from '@lucide/svelte';

  const appId = $derived(Number(page.params.id));

  let app = $state<ApplicationEntry | null>(null);
  let loading = $state(true);
  let error = $state('');

  // Step states
  let scraping = $state(false);
  let jobDesc = $state('');
  let savingDesc = $state(false);

  let generatingCv = $state(false);
  let cvProfile = $state<ProfileData | null>(null);
  let cvLanguage = $state<'en' | 'fr'>('en');

  let generatingCl = $state(false);
  let clText = $state('');
  let clLanguage = $state<'en' | 'fr'>('en');

  // Load application
  $effect(() => {
    loading = true;
    error = '';
    getApplication(appId)
      .then(a => {
        app = a;
        jobDesc = a.job_description ?? '';
        // Proactively load linked docs for the activity log
        if (a.linked_cv_id) getCvHistoryEntry(a.linked_cv_id).then(e => { cvEntry = e; }).catch(() => {});
        if (a.linked_cover_letter_id) getCoverLetterHistoryEntry(a.linked_cover_letter_id).then(e => { clEntry = e; }).catch(() => {});
      })
      .catch(e => { error = errorMessage(e); })
      .finally(() => { loading = false; });
  });

  async function refresh() {
    const a = await getApplication(appId).catch(() => null);
    if (a) { app = a; jobDesc = a.job_description ?? jobDesc; }
  }

  // ── Step 1: Scrape job from URL ──────────────────────────────────────────
  async function scrape() {
    if (!app?.job_url) return;
    scraping = true;
    try {
      const result = await scrapeAnalyze({ url: app.job_url });
      jobDesc = result.job_description;
      // Patch application with scraped details
      const patch: Record<string, unknown> = { job_description: result.job_description };
      if (result.company_name && !app.company_name) patch.company_name = result.company_name;
      if (result.role_title && !app.role_title) patch.role_title = result.role_title;
      if (result.location && !app.location) patch.location = result.location;
      if (result.salary && !app.salary) patch.salary = result.salary;
      await updateApplication(appId, patch);
      await refresh();
      toastState.success('Job details scraped successfully.');
    } catch (e) {
      toastState.error(`Scrape failed: ${errorMessage(e)}`);
    } finally {
      scraping = false;
    }
  }

  async function saveDesc() {
    savingDesc = true;
    try {
      await updateApplication(appId, { job_description: jobDesc });
      await refresh();
      toastState.success('Job description saved.');
    } catch (e) {
      toastState.error(errorMessage(e));
    } finally {
      savingDesc = false;
    }
  }

  // ── Step 2: Generate tailored CV ─────────────────────────────────────────
  async function generateCv() {
    const ap = activeProfile.current;
    if (!ap) { toastState.error('Select a profile first.'); return; }
    if (!jobDesc.trim()) { toastState.error('Add a job description in Step 1 first.'); return; }
    generatingCv = true;
    cvProfile = null;
    try {
      const resp = await generateCvStream({
        profile_id: ap.id,
        job_description: jobDesc,
        enhance: true,
        application_id: appId,
        language: cvLanguage,
      });
      await consumeStructuredStream(resp, {
        onEvent(event, data) {
          if (event === 'done') {
            const d = data as { profile: ProfileData; enhanced: boolean };
            cvProfile = d.profile;
            toastState.success('Tailored resume generated and linked.');
            refresh();
          } else if (event === 'rate_limit') {
            toastState.error('Rate limit — please wait and retry.');
          }
        },
        onError: (msg) => toastState.error(`CV generation failed: ${msg}`),
      });
    } catch (e) {
      toastState.error(errorMessage(e));
    } finally {
      generatingCv = false;
    }
  }

  // ── Step 3: Generate cover letter ────────────────────────────────────────
  async function generateCl() {
    const ap = activeProfile.current;
    if (!ap) { toastState.error('Select a profile first.'); return; }
    if (!jobDesc.trim()) { toastState.error('Add a job description in Step 1 first.'); return; }
    generatingCl = true;
    clText = '';
    try {
      const resp = await generateCoverLetterStream({
        profile_id: ap.id,
        job_description: jobDesc,
        company_name: app?.company_name ?? undefined,
        role_title: app?.role_title ?? undefined,
        location: app?.location ?? undefined,
        job_url: app?.job_url ?? undefined,
        application_id: appId,
        language: clLanguage,
      });
      // Cover letter uses text stream (chunks)
      if (!resp.body) throw new Error('No response body');
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      let currentEvent = 'message';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim(); continue; }
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6);
          try {
            const parsed = JSON.parse(raw);
            const d = typeof parsed === 'string' ? JSON.parse(parsed) : parsed;
            if (currentEvent === 'done' || d.done) {
              toastState.success('Cover letter generated and linked.');
              refresh();
              break;
            }
            if (d.chunk) clText += d.chunk;
          } catch {
            // plain chunk
            if (raw !== '[DONE]') clText += raw;
          }
          currentEvent = 'message';
        }
      }
    } catch (e) {
      toastState.error(errorMessage(e));
    } finally {
      generatingCl = false;
    }
  }

  const hasDesc = $derived(!!app?.job_description);
  const hasCV   = $derived(!!app?.linked_cv_id);
  const hasCL   = $derived(!!app?.linked_cover_letter_id);

  // ── Auto-pipeline ─────────────────────────────────────────────────────────
  // Fires once after initial load when job description exists but docs are missing.
  let autoPipelineRan = $state(false);
  let autoPipelineRunning = $state(false);
  let autoStep = $state<'idle' | 'cv' | 'cl' | 'score' | 'done'>('idle');

  $effect(() => {
    // Wait until load is complete and app is loaded
    if (loading || !app || autoPipelineRan) return;
    // Only auto-run if there's a job description but no documents yet
    if (!app.job_description || app.linked_cv_id || app.linked_cover_letter_id) {
      autoPipelineRan = true;
      return;
    }
    autoPipelineRan = true;
    runAutoPipeline();
  });

  async function runAutoPipeline() {
    const ap = activeProfile.current;
    if (!ap || !app?.job_description) return;
    autoPipelineRunning = true;

    // Step 1: Generate CV
    autoStep = 'cv';
    let cvId: number | null = null;
    try {
      const resp = await generateCvStream({
        profile_id: ap.id,
        job_description: app.job_description,
        enhance: true,
        application_id: appId,
      });
      await consumeStructuredStream(resp, {
        onEvent(event, data) {
          if (event === 'done') {
            const d = data as { profile: ProfileData; enhanced: boolean; id?: number };
            cvProfile = d.profile;
            cvId = d.id ?? null;
          } else if (event === 'rate_limit') {
            toastState.error('Rate limit hit — resume generation paused.');
          }
        },
        onError: (msg) => toastState.error(`Auto CV: ${msg}`),
      });
      await refresh();
    } catch (e) {
      toastState.error(`Auto CV generation failed: ${errorMessage(e)}`);
      autoPipelineRunning = false;
      autoStep = 'idle';
      return;
    }

    // Step 2: Generate Cover Letter
    autoStep = 'cl';
    let generatedClId: number | null = null;
    try {
      const clResp = await generateCoverLetterStream({
        profile_id: ap.id,
        job_description: app.job_description,
        company_name: app.company_name ?? undefined,
        role_title: app.role_title ?? undefined,
        location: app.location ?? undefined,
        job_url: app.job_url ?? undefined,
        application_id: appId,
      });
      if (!clResp.body) throw new Error('No response body');
      const reader = clResp.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      let currentEvent = 'message';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim(); continue; }
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6);
          try {
            const parsed = JSON.parse(raw);
            const d = typeof parsed === 'string' ? JSON.parse(parsed) : parsed;
            if (currentEvent === 'done' || d.done) break;
            if (d.chunk) clText += d.chunk;
            if (d.id) generatedClId = d.id;
          } catch {
            if (raw !== '[DONE]') clText += raw;
          }
          currentEvent = 'message';
        }
      }
      await refresh();
    } catch (e) {
      toastState.error(`Auto cover letter failed: ${errorMessage(e)}`);
      autoPipelineRunning = false;
      autoStep = 'idle';
      return;
    }

    // Step 3: Score with tailored CV
    autoStep = 'score';
    try {
      // Use the CV id from the done event, or fall back to app's linked_cv_id
      const cvIdToScore = cvId ?? app?.linked_cv_id;
      if (cvIdToScore && app?.job_description) {
        rescoreResult = await analyzeFitWithCv(cvIdToScore, app.job_description);
        rescoreExpanded = true;
      }
    } catch (e) {
      toastState.error(`Auto score failed: ${errorMessage(e)}`);
    }

    autoStep = 'done';
    autoPipelineRunning = false;
    toastState.success('Pipeline complete — resume, cover letter, and ATS score ready!');
  }

  // ── ATS Re-score with tailored CV ────────────────────────────────────────
  let rescoring = $state(false);
  let rescoreResult = $state<FitAnalysisResponse | null>(null);
  let rescoreExpanded = $state(false);
  let regeneratingWithKeywords = $state(false);

  async function rescoreWithCv() {
    if (!app?.linked_cv_id || !app.job_description) return;
    rescoring = true;
    rescoreResult = null;
    try {
      rescoreResult = await analyzeFitWithCv(app.linked_cv_id, app.job_description);
      rescoreExpanded = true;
      toastState.success(`Updated ATS score: ${rescoreResult.match_score}%`);
    } catch (e) {
      toastState.error(`Re-score failed: ${errorMessage(e)}`);
    } finally {
      rescoring = false;
    }
  }

  async function regenerateCvWithKeywords() {
    const ap = activeProfile.current;
    if (!ap || !rescoreResult) return;
    regeneratingWithKeywords = true;
    cvProfile = null;
    try {
      const parts: string[] = [];
      if (rescoreResult.missing_keywords.length) {
        parts.push(`Please incorporate these missing keywords naturally where relevant: ${rescoreResult.missing_keywords.join(', ')}.`);
      }
      if (rescoreResult.cons.length) {
        parts.push(`Try to address these gaps where you can honestly frame existing experience: ${rescoreResult.cons.join(' ')}`);
      }
      const extraContext = parts.join('\n');
      const resp = await generateCvStream({
        profile_id: ap.id,
        job_description: app?.job_description ?? jobDesc,
        enhance: true,
        application_id: appId,
        extra_context: extraContext,
      });
      await consumeStructuredStream(resp, {
        onEvent(event, data) {
          if (event === 'done') {
            const d = data as { profile: ProfileData; enhanced: boolean };
            cvProfile = d.profile;
            toastState.success('New resume version generated with missing keywords.');
            refresh();
          } else if (event === 'rate_limit') {
            toastState.error('Rate limit — please wait and retry.');
          }
        },
        onError: (msg) => toastState.error(`Regeneration failed: ${msg}`),
      });
    } catch (e) {
      toastState.error(errorMessage(e));
    } finally {
      regeneratingWithKeywords = false;
    }
  }

  function scoreColor(score: number | null | undefined): string {
    if (score == null) return 'text-muted-foreground';
    if (score >= 80) return 'text-emerald-600 dark:text-emerald-400';
    if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-500 dark:text-red-400';
  }

  // ── Linked document entries (for log + preview) ───────────────────────────
  let cvEntry  = $state<GeneratedCVEntry | null>(null);
  let clEntry  = $state<GeneratedCoverLetterEntry | null>(null);

  // ── Inline document preview ───────────────────────────────────────────────
  type PreviewType = 'cv' | 'cl' | null;
  let previewType = $state<PreviewType>(null);
  let previewCv = $state<GeneratedCVEntry | null>(null);
  let previewCl = $state<GeneratedCoverLetterEntry | null>(null);
  let previewLoading = $state(false);
  let downloading = $state(false);

  function parseCvProfile(): ProfileData | null {
    if (!previewCv) return null;
    try { return JSON.parse(previewCv.profile_snapshot) as ProfileData; } catch { return null; }
  }

  async function openCvPreview() {
    if (!app?.linked_cv_id) return;
    previewType = 'cv';
    if (cvEntry) { previewCv = cvEntry; return; }
    previewLoading = true;
    try {
      previewCv = await getCvHistoryEntry(app.linked_cv_id);
      cvEntry = previewCv;
    } catch (e) {
      toastState.error(`Could not load resume: ${errorMessage(e)}`);
      previewType = null;
    } finally {
      previewLoading = false;
    }
  }

  async function openClPreview() {
    if (!app?.linked_cover_letter_id) return;
    previewType = 'cl';
    if (clEntry) { previewCl = clEntry; return; }
    previewLoading = true;
    try {
      previewCl = await getCoverLetterHistoryEntry(app.linked_cover_letter_id);
      clEntry = previewCl;
    } catch (e) {
      toastState.error(`Could not load cover letter: ${errorMessage(e)}`);
      previewType = null;
    } finally {
      previewLoading = false;
    }
  }

  function closePreview() {
    previewType = null;
    previewCv = null;
    previewCl = null;
  }

  async function downloadCv() {
    const profile = parseCvProfile();
    if (!profile) return;
    downloading = true;
    try {
      const blob = await generateCvPdf({ profile, language: previewCv?.language ?? 'en' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = pdfFilename('resume', {
        position: app?.role_title,
        company: app?.company_name,
        name: activeProfile.current?.name,
      });
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toastState.error(errorMessage(e)); }
    finally { downloading = false; }
  }

  async function downloadCl() {
    if (!previewCl) return;
    downloading = true;
    try {
      const clProfile = parseCvProfile();
      const blob = await generateCoverLetterPdf({
        text: previewCl.cover_letter_text,
        language: previewCl.language ?? 'en',
        name: clProfile?.name ?? activeProfile.current?.name,
        email: clProfile?.email,
        phone: clProfile?.phone,
        location: clProfile?.location,
        linkedin: clProfile?.linkedin,
        github: clProfile?.github,
        portfolio: clProfile?.portfolio,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = pdfFilename('cover_letter', {
        position: app?.role_title,
        company: app?.company_name,
        name: activeProfile.current?.name,
      });
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toastState.error(errorMessage(e)); }
    finally { downloading = false; }
  }

  const STATUS_COLORS: Record<string, string> = {
    applied: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    interviewing: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
    offer: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    rejected: 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400',
  };

  const STATUS_LABELS: Record<string, string> = {
    applied: '✓ Applied',
    interviewing: '🗓 Interviewing',
    offer: '🎉 Offer!',
    rejected: '✗ Rejected',
  };

  function stepStatus(done: boolean) {
    return done ? 'done' : 'pending';
  }

  function safeHostname(url: string | null | undefined): string {
    if (!url) return 'unknown';
    try {
      return new URL(url.match(/^https?:\/\//) ? url : `https://${url}`).hostname;
    } catch {
      return url.split('/')[0].split('?')[0] || 'unknown';
    }
  }
</script>

{#if loading}
  <div class="flex items-center justify-center py-24 text-muted-foreground gap-3">
    <Loader class="w-5 h-5 animate-spin" />
    <span class="text-sm">Loading application...</span>
  </div>
{:else if error || !app}
  <div class="py-16 text-center text-muted-foreground">
    <p class="text-sm">{error || 'Application not found.'}</p>
    <Button variant="outline" class="mt-4" onclick={() => goto('/tracker')}>
      <ArrowLeft class="w-4 h-4 mr-2" /> Back to Tracker
    </Button>
  </div>
{:else}
  <!-- Header -->
  <div class="mb-6">
    <button
      onclick={() => goto('/tracker')}
      class="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground mb-3 transition-colors"
    >
      <ArrowLeft class="w-3.5 h-3.5" /> Tracker
    </button>
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold">{app.company_name || 'Unknown Company'}</h1>
        <p class="text-muted-foreground mt-0.5">{app.role_title || 'No Role Title'}</p>
      </div>
      <span class="text-xs font-bold px-3 py-1.5 rounded-full capitalize shrink-0 {STATUS_COLORS[app.status] ?? 'bg-muted text-muted-foreground'}">
        {STATUS_LABELS[app.status] ?? app.status}
      </span>
    </div>

    <!-- Progress pills -->
    <div class="flex gap-2 mt-4">
      {#each [
        { label: 'Job Details', done: hasDesc },
        { label: 'Resume',      done: hasCV   },
        { label: 'Cover Letter',done: hasCL   },
        { label: 'Interview',   done: false   },
      ] as step, i}
        <div class="flex items-center gap-1.5">
          {#if i > 0}<span class="text-muted-foreground/40 text-xs">›</span>{/if}
          <span class="flex items-center gap-1 text-xs font-medium {step.done ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground'}">
            {#if step.done}
              <CheckCircle class="w-3.5 h-3.5" />
            {:else}
              <CircleDashed class="w-3.5 h-3.5" />
            {/if}
            {step.label}
          </span>
        </div>
      {/each}
    </div>
  </div>

  <div class="max-w-2xl space-y-4">

    <!-- ── Auto-pipeline banner ─────────────────────────────────────────── -->
    {#if autoPipelineRunning || autoStep === 'done'}
      <div class="rounded-xl border {autoStep === 'done' ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-primary/20 bg-primary/5'} p-4">
        <div class="flex items-center gap-3 mb-3">
          {#if autoStep === 'done'}
            <CheckCircle class="w-4 h-4 text-emerald-500 shrink-0" />
            <p class="text-sm font-semibold text-emerald-600 dark:text-emerald-400">Pipeline complete</p>
          {:else}
            <Loader class="w-4 h-4 animate-spin text-primary shrink-0" />
            <p class="text-sm font-semibold">Auto-generating documents…</p>
          {/if}
        </div>
        <div class="flex items-center gap-2 text-xs">
          {#each [
            { key: 'cv',    label: 'Tailored Resume',  color: 'purple' },
            { key: 'cl',    label: 'Cover Letter',     color: 'blue'   },
            { key: 'score', label: 'ATS Score',        color: 'amber'  },
          ] as s}
            {@const steps = ['cv', 'cl', 'score', 'done']}
            {@const stepIdx = steps.indexOf(s.key)}
            {@const curIdx  = steps.indexOf(autoStep)}
            {@const done    = curIdx > stepIdx || autoStep === 'done'}
            {@const active  = autoStep === s.key}
            <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg
              {done  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' :
               active ? 'bg-primary/10 text-primary' :
                        'bg-muted/60 text-muted-foreground'}">
              {#if done}
                <CheckCircle class="w-3 h-3 shrink-0" />
              {:else if active}
                <Loader class="w-3 h-3 animate-spin shrink-0" />
              {:else}
                <CircleDashed class="w-3 h-3 shrink-0" />
              {/if}
              {s.label}
            </div>
            {#if s.key !== 'score'}<span class="text-muted-foreground/40">›</span>{/if}
          {/each}
        </div>
      </div>
    {/if}

    <!-- ── Step 1: Job Details ──────────────────────────────────────────── -->
    <Card>
      <CardContent class="pt-5 space-y-4">
        <div class="flex items-center gap-2">
          <span class="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center shrink-0">1</span>
          <h2 class="font-semibold">Job Details</h2>
          {#if hasDesc}<CheckCircle class="w-4 h-4 text-green-500 ml-auto" />{/if}
        </div>

        {#if app.job_url}
          <div class="flex items-center gap-2">
            <a
              href={app.job_url}
              target="_blank"
              rel="noopener noreferrer"
              class="text-xs text-primary hover:underline truncate flex items-center gap-1 flex-1"
            >
              <ExternalLink class="w-3 h-3 shrink-0" />
              {app.job_url}
            </a>
            <Button
              variant="outline"
              size="sm"
              onclick={scrape}
              disabled={scraping}
              class="shrink-0"
            >
              {#if scraping}
                <Loader class="w-3.5 h-3.5 mr-1.5 animate-spin" />
                Scraping...
              {:else}
                <Search class="w-3.5 h-3.5 mr-1.5" />
                Scrape job
              {/if}
            </Button>
          </div>
        {/if}

        <div class="space-y-2">
          <p class="text-xs font-medium text-muted-foreground">Job Description</p>
          <Textarea
            placeholder="Paste the full job description here, or click 'Scrape job' above to auto-fill from the URL."
            bind:value={jobDesc}
            rows={8}
          />
          <Button
            variant="outline"
            size="sm"
            onclick={saveDesc}
            disabled={savingDesc || jobDesc === (app.job_description ?? '')}
          >
            {savingDesc ? 'Saving...' : 'Save description'}
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- ── Step 2: Tailored Resume ──────────────────────────────────────── -->
    <Card class="{!hasDesc ? 'opacity-60' : ''}">
      <CardContent class="pt-5 space-y-3">
        <div class="flex items-center gap-2">
          <span class="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center shrink-0">2</span>
          <h2 class="font-semibold">Tailored Resume</h2>
          {#if hasCV}<CheckCircle class="w-4 h-4 text-green-500 ml-auto" />{/if}
        </div>

        {#if hasCV}
          <div class="flex items-center gap-2">
            <p class="text-xs text-green-600 dark:text-green-400">Resume generated and linked to this application.</p>
            {#if cvEntry?.language === 'fr'}
              <span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">🇫🇷 FR</span>
            {:else if cvEntry?.language === 'en'}
              <span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-muted text-muted-foreground">🇬🇧 EN</span>
            {/if}
          </div>
          <div class="flex gap-2">
            <Button variant="outline" size="sm" class="flex-1" onclick={openCvPreview} disabled={previewLoading}>
              <FileText class="w-3.5 h-3.5 mr-1.5" /> View resume
            </Button>
            <Button variant="ghost" size="sm" onclick={generateCv} disabled={generatingCv || !hasDesc}>
              <RefreshCw class="w-3.5 h-3.5 mr-1.5 {generatingCv ? 'animate-spin' : ''}" /> Regenerate
            </Button>
          </div>
        {:else}
          <p class="text-xs text-muted-foreground">Generate a resume tailored to this specific job description using your active profile.</p>
          <!-- Language toggle -->
          <div class="flex gap-1 w-fit">
            {#each [{ v: 'en', label: '🇬🇧 EN' }, { v: 'fr', label: '🇫🇷 FR' }] as lang}
              <button
                onclick={() => cvLanguage = lang.v as 'en' | 'fr'}
                class="px-3 py-1 rounded-md text-xs font-semibold border transition-all
                  {cvLanguage === lang.v
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-muted text-muted-foreground border-border hover:border-primary/40'}"
              >{lang.label}</button>
            {/each}
          </div>
          <Button
            onclick={generateCv}
            disabled={generatingCv || !hasDesc}
            class="w-full"
          >
            {#if generatingCv}
              <Loader class="w-4 h-4 mr-2 animate-spin" /> Generating resume...
            {:else}
              Generate tailored resume {cvLanguage === 'fr' ? '(Français)' : ''}
            {/if}
          </Button>
          {#if !hasDesc}
            <p class="text-xs text-muted-foreground">Add a job description in Step 1 first.</p>
          {/if}
        {/if}
      </CardContent>
    </Card>

    <!-- ── ATS Match Score ────────────────────────────────────────────────── -->
    {#if hasCV && hasDesc}
      <Card>
        <CardContent class="pt-5 space-y-3">
          <div class="flex items-center gap-2">
            <TrendingUp class="w-4 h-4 text-primary shrink-0" />
            <h2 class="font-semibold">ATS Match Score</h2>
          </div>

          <!-- Score row -->
          <div class="flex items-center gap-4">
            <!-- Original score -->
            <div class="flex flex-col items-center rounded-lg bg-muted/60 px-4 py-3 min-w-[80px]">
              <span class="text-xs text-muted-foreground mb-0.5">Original</span>
              <span class={`text-2xl font-black ${scoreColor(app.match_score)}`}>
                {app.match_score != null ? `${app.match_score}%` : '—'}
              </span>
              <span class="text-[10px] text-muted-foreground">raw profile</span>
            </div>

            {#if rescoreResult}
              <div class="flex flex-col items-center gap-1 text-muted-foreground">
                <span class="text-xl">→</span>
                {#if rescoreResult.match_score > (app.match_score ?? 0)}
                  <span class="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
                    +{rescoreResult.match_score - (app.match_score ?? 0)}pts
                  </span>
                {:else if rescoreResult.match_score < (app.match_score ?? 0)}
                  <span class="text-[10px] text-red-500 font-medium">
                    {rescoreResult.match_score - (app.match_score ?? 0)}pts
                  </span>
                {:else}
                  <span class="text-[10px] text-muted-foreground">no change</span>
                {/if}
              </div>

              <!-- New score -->
              <div class="flex flex-col items-center rounded-lg border-2 border-primary/20 bg-primary/5 px-4 py-3 min-w-[80px]">
                <span class="text-xs text-muted-foreground mb-0.5">After tailoring</span>
                <span class={`text-2xl font-black ${scoreColor(rescoreResult.match_score)}`}>
                  {rescoreResult.match_score}%
                </span>
                <span class="text-[10px] text-muted-foreground">tailored CV</span>
              </div>
            {:else}
              <div class="flex-1 text-xs text-muted-foreground">
                <p>Score calculated against your raw profile.</p>
                <p class="mt-0.5">Re-score to see how the tailored resume performs.</p>
              </div>
            {/if}
          </div>

          <!-- Re-score button -->
          <Button
            variant="outline"
            size="sm"
            onclick={rescoreWithCv}
            disabled={rescoring}
            class="w-full"
          >
            {#if rescoring}
              <Loader class="w-3.5 h-3.5 mr-1.5 animate-spin" /> Scoring tailored resume...
            {:else}
              <Sparkles class="w-3.5 h-3.5 mr-1.5" />
              {rescoreResult ? 'Re-score again' : 'Score with tailored resume'}
            {/if}
          </Button>

          <!-- Expandable breakdown -->
          {#if rescoreResult}
            <button
              onclick={() => rescoreExpanded = !rescoreExpanded}
              class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors w-full"
            >
              {#if rescoreExpanded}
                <ChevronUp class="w-3.5 h-3.5" />
              {:else}
                <ChevronDown class="w-3.5 h-3.5" />
              {/if}
              {rescoreExpanded ? 'Hide' : 'Show'} full breakdown
            </button>

            {#if rescoreExpanded}
              <div class="space-y-3 pt-1 border-t border-border">
                {#if rescoreResult.pros.length}
                  <div>
                    <p class="text-xs font-medium text-emerald-600 dark:text-emerald-400 mb-1">Strengths</p>
                    <ul class="space-y-0.5">
                      {#each rescoreResult.pros as p}
                        <li class="text-xs text-muted-foreground flex gap-1.5"><span class="shrink-0">·</span>{p}</li>
                      {/each}
                    </ul>
                  </div>
                {/if}
                {#if rescoreResult.cons.length}
                  <div>
                    <p class="text-xs font-medium text-red-500 mb-1">Gaps</p>
                    <ul class="space-y-0.5">
                      {#each rescoreResult.cons as c}
                        <li class="text-xs text-muted-foreground flex gap-1.5"><span class="shrink-0">·</span>{c}</li>
                      {/each}
                    </ul>
                  </div>
                {/if}
                {#if rescoreResult.missing_keywords.length}
                  <div>
                    <p class="text-xs font-medium text-yellow-600 dark:text-yellow-400 mb-1">Missing keywords</p>
                    <div class="flex flex-wrap gap-1 mb-2">
                      {#each rescoreResult.missing_keywords as kw}
                        <span class="text-[11px] px-1.5 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300">{kw}</span>
                      {/each}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onclick={regenerateCvWithKeywords}
                      disabled={regeneratingWithKeywords}
                      class="w-full border-dashed border-yellow-400/60 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-50 dark:hover:bg-yellow-900/20"
                    >
                      {#if regeneratingWithKeywords}
                        <Loader class="w-3.5 h-3.5 mr-1.5 animate-spin" /> Regenerating resume…
                      {:else}
                        <RefreshCw class="w-3.5 h-3.5 mr-1.5" /> Regenerate resume with these keywords
                      {/if}
                    </Button>
                  </div>
                {/if}
                {#if rescoreResult.suggested_emphasis}
                  <div>
                    <p class="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1">Suggested emphasis</p>
                    <p class="text-xs text-muted-foreground">{rescoreResult.suggested_emphasis}</p>
                  </div>
                {/if}
                {#if rescoreResult.red_flags.length}
                  <div>
                    <p class="text-xs font-medium text-red-600 dark:text-red-400 mb-1">Red flags</p>
                    <ul class="space-y-0.5">
                      {#each rescoreResult.red_flags as f}
                        <li class="text-xs text-muted-foreground flex gap-1.5"><span class="shrink-0">⚑</span>{f}</li>
                      {/each}
                    </ul>
                  </div>
                {/if}
              </div>
            {/if}
          {/if}

        </CardContent>
      </Card>
    {/if}

    <!-- ── Step 3: Cover Letter ─────────────────────────────────────────── -->
    <Card class="{!hasDesc ? 'opacity-60' : ''}">
      <CardContent class="pt-5 space-y-3">
        <div class="flex items-center gap-2">
          <span class="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center shrink-0">3</span>
          <h2 class="font-semibold">Cover Letter</h2>
          {#if hasCL}<CheckCircle class="w-4 h-4 text-green-500 ml-auto" />{/if}
        </div>

        {#if hasCL}
          <p class="text-xs text-green-600 dark:text-green-400">Cover letter generated and linked to this application.</p>
          <div class="flex gap-2">
            <Button variant="outline" size="sm" class="flex-1" onclick={openClPreview} disabled={previewLoading}>
              <FileText class="w-3.5 h-3.5 mr-1.5" /> View cover letter
            </Button>
            <Button variant="ghost" size="sm" onclick={generateCl} disabled={generatingCl || !hasDesc}>
              <RefreshCw class="w-3.5 h-3.5 mr-1.5 {generatingCl ? 'animate-spin' : ''}" /> Regenerate
            </Button>
          </div>
        {:else}
          <p class="text-xs text-muted-foreground">Generate a cover letter tailored to {app.company_name || 'this company'} and this specific role.</p>
          <!-- Language toggle -->
          <div class="flex gap-1 w-fit">
            {#each [{ v: 'en', label: '🇬🇧 EN' }, { v: 'fr', label: '🇫🇷 FR' }] as lang}
              <button
                onclick={() => clLanguage = lang.v as 'en' | 'fr'}
                class="px-3 py-1 rounded-md text-xs font-semibold border transition-all
                  {clLanguage === lang.v
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-muted text-muted-foreground border-border hover:border-primary/40'}"
              >{lang.label}</button>
            {/each}
          </div>
          <Button
            onclick={generateCl}
            disabled={generatingCl || !hasDesc}
            class="w-full"
          >
            {#if generatingCl}
              <Loader class="w-4 h-4 mr-2 animate-spin" /> Generating cover letter...
            {:else}
              Generate cover letter {clLanguage === 'fr' ? '(Français)' : ''}
            {/if}
          </Button>
          {#if clText}
            <div class="rounded-lg bg-muted/50 p-3 text-xs leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto border">
              {clText}
            </div>
          {/if}
          {#if !hasDesc}
            <p class="text-xs text-muted-foreground">Add a job description in Step 1 first.</p>
          {/if}
        {/if}
      </CardContent>
    </Card>

    <!-- ── Step 4: Interview Practice ──────────────────────────────────── -->
    <Card>
      <CardContent class="pt-5 space-y-3">
        <div class="flex items-center gap-2">
          <span class="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center shrink-0">4</span>
          <h2 class="font-semibold">Interview Practice</h2>
        </div>
        <p class="text-xs text-muted-foreground">
          Practice answering interview questions with AI coaching, voice playback, and live scoring — all tailored to this specific job.
        </p>
        <Button
          onclick={() => goto(`/interview?app_id=${appId}`)}
          class="w-full"
          variant={hasDesc ? 'default' : 'outline'}
        >
          <Mic class="w-4 h-4 mr-2" />
          {hasDesc ? 'Start interview practice' : 'Start practice (no JD — generic questions)'}
        </Button>
      </CardContent>
    </Card>

    <!-- ── Application Log ──────────────────────────────────────────────── -->
    <Card>
      <CardContent class="pt-5 space-y-4">
        <div class="flex items-center gap-2">
          <ClipboardList class="w-4 h-4 text-primary shrink-0" />
          <h2 class="font-semibold">Application Log</h2>
        </div>

        <!-- Timeline -->
        <ol class="relative border-l border-border ml-3 space-y-0 pb-1">

          <!-- Created -->
          <li class="mb-5 ml-5">
            <div class="absolute -left-1.5 mt-0.5 w-3 h-3 rounded-full bg-muted border-2 border-border"></div>
            <p class="text-xs font-medium">Added to tracker</p>
            <p class="text-[11px] text-muted-foreground">{formatDate(app.created_at)}</p>
            <p class="text-[11px] text-muted-foreground">
              {app.profile_icon ?? ''} {app.profile_label ?? 'Default profile'}
              {#if app.location} · {app.location}{/if}
              {#if app.salary} · {app.salary}{/if}
            </p>
          </li>

          <!-- Job description -->
          {#if hasDesc}
            <li class="mb-5 ml-5">
              <div class="absolute -left-1.5 mt-0.5 w-3 h-3 rounded-full bg-blue-400 border-2 border-background"></div>
              <p class="text-xs font-medium">Job description added</p>
              {#if app.job_url}
                <p class="text-[11px] text-muted-foreground">
                  Source: <a href={app.job_url} target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">{safeHostname(app.job_url)}</a>
                </p>
              {/if}
              <p class="text-[11px] text-muted-foreground">{(app.job_description ?? '').slice(0, 120).trim()}…</p>
            </li>
          {/if}

          <!-- Resume generated -->
          {#if hasCV && cvEntry}
            <li class="mb-5 ml-5">
              <div class="absolute -left-1.5 mt-0.5 w-3 h-3 rounded-full bg-purple-400 border-2 border-background"></div>
              <p class="text-xs font-medium">Tailored resume generated</p>
              <p class="text-[11px] text-muted-foreground">
                {formatDate(cvEntry.created_at)}
                · {cvEntry.enhanced ? 'ATS-enhanced' : 'Standard'}
              </p>
              <button onclick={openCvPreview} class="text-[11px] text-primary hover:underline mt-0.5">View resume →</button>
            </li>
          {:else if hasCV}
            <li class="mb-5 ml-5">
              <div class="absolute -left-1.5 mt-0.5 w-3 h-3 rounded-full bg-purple-400 border-2 border-background"></div>
              <p class="text-xs font-medium">Tailored resume generated</p>
              <button onclick={openCvPreview} class="text-[11px] text-primary hover:underline mt-0.5">View resume →</button>
            </li>
          {/if}

          <!-- Cover letter generated -->
          {#if hasCL && clEntry}
            <li class="mb-5 ml-5">
              <div class="absolute -left-1.5 mt-0.5 w-3 h-3 rounded-full bg-indigo-400 border-2 border-background"></div>
              <p class="text-xs font-medium">Cover letter generated</p>
              <p class="text-[11px] text-muted-foreground">
                {formatDate(clEntry.created_at)}
                · {clEntry.tone} tone
                {#if clEntry.match_score} · <span class="text-emerald-600 dark:text-emerald-400 font-medium">{clEntry.match_score}% match</span>{/if}
              </p>
              <p class="text-[11px] text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">
                "{clEntry.cover_letter_text.slice(0, 180).trim()}…"
              </p>
              <button onclick={openClPreview} class="text-[11px] text-primary hover:underline mt-0.5">View cover letter →</button>
            </li>
          {:else if hasCL}
            <li class="mb-5 ml-5">
              <div class="absolute -left-1.5 mt-0.5 w-3 h-3 rounded-full bg-indigo-400 border-2 border-background"></div>
              <p class="text-xs font-medium">Cover letter generated</p>
              <button onclick={openClPreview} class="text-[11px] text-primary hover:underline mt-0.5">View cover letter →</button>
            </li>
          {/if}

          <!-- Applied -->
          {#if app.status === 'applied' || app.status === 'interviewing' || app.status === 'offer' || app.status === 'rejected'}
            <li class="ml-5">
              <div class="absolute -left-1.5 mt-0.5 w-3 h-3 rounded-full bg-emerald-500 border-2 border-background"></div>
              <p class="text-xs font-semibold text-emerald-600 dark:text-emerald-400">✓ Application submitted</p>
              <p class="text-[11px] text-muted-foreground">
                {app.applied_date
                  ? formatDateShort(app.applied_date)
                  : formatDate(app.created_at)}
                · via {app.job_url ? safeHostname(app.job_url) : 'manual'}
              </p>
              {#if !hasCV && !hasCL}
                <p class="text-[11px] text-muted-foreground mt-0.5">No documents linked — applied manually.</p>
              {:else}
                <div class="flex gap-3 mt-1">
                  {#if hasCV}
                    <span class="text-[11px] bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 px-1.5 py-0.5 rounded">📄 Resume attached</span>
                  {/if}
                  {#if hasCL}
                    <span class="text-[11px] bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded">✉️ Cover letter attached</span>
                  {/if}
                </div>
              {/if}
            </li>
          {:else}
            <li class="ml-5">
              <div class="absolute -left-1.5 mt-0.5 w-3 h-3 rounded-full bg-background border-2 border-dashed border-border"></div>
              <p class="text-[11px] text-muted-foreground italic">Not yet applied</p>
            </li>
          {/if}

        </ol>

        <!-- Notes -->
        {#if app.notes}
          <div class="rounded-lg bg-muted/40 px-3 py-2.5 text-xs">
            <p class="font-medium text-muted-foreground mb-1">Notes</p>
            <p class="leading-relaxed">{app.notes}</p>
          </div>
        {/if}

      </CardContent>
    </Card>

  </div>
{/if}

<!-- ── Document preview slide-over ───────────────────────────────────────────── -->
{#if previewType}
  <!-- Backdrop -->
  <div
    class="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
    onclick={closePreview}
    role="presentation"
    aria-hidden="true"
  ></div>

  <!-- Panel -->
  <div class="fixed inset-y-0 right-0 z-50 w-full max-w-2xl bg-card shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
    <!-- Header -->
    <div class="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/20 shrink-0">
      <div>
        <h2 class="font-bold text-base">
          {previewType === 'cv' ? 'Tailored Resume' : 'Cover Letter'}
        </h2>
        <p class="text-xs text-muted-foreground mt-0.5">{app?.role_title} @ {app?.company_name}</p>
      </div>
      <div class="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onclick={previewType === 'cv' ? downloadCv : downloadCl}
          disabled={downloading || previewLoading}
        >
          <Download class="w-3.5 h-3.5 mr-1.5" />
          {downloading ? 'Downloading…' : 'Download PDF'}
        </Button>
        <button
          onclick={closePreview}
          class="p-1.5 rounded-md hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
          aria-label="Close"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto">
      {#if previewLoading}
        <div class="flex items-center justify-center h-48 gap-3 text-muted-foreground">
          <Loader class="w-5 h-5 animate-spin" />
          <span class="text-sm">Loading…</span>
        </div>
      {:else if previewType === 'cv' && previewCv}
        {@const profile = parseCvProfile()}
        {#if profile}
          <CvPreview {profile} />
        {:else}
          <p class="p-8 text-sm text-destructive">Could not parse resume.</p>
        {/if}
      {:else if previewType === 'cl' && previewCl}
        <div class="p-6 max-w-prose mx-auto">
          <CoverLetterPreview text={previewCl.cover_letter_text} />
        </div>
      {/if}
    </div>
  </div>
{/if}
