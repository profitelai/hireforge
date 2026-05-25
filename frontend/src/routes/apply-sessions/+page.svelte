<script lang="ts">
  import { activeProfile } from '$lib/activeProfile.svelte';
  import { deleteApplySession, listApplySessions } from '$lib/api';
  import { toastState } from '$lib/toast.svelte';
  import type { ApplySession } from '$lib/types';
  import {
    BookOpen,
    Building2,
    CheckCircle2,
    Circle,
    Clock,
    ExternalLink,
    FileText,
    Loader2,
    TriangleAlert,
    Trash2,
    Zap,
  } from '@lucide/svelte';

  let sessions = $state<ApplySession[]>([]);
  let total = $state(0);
  let loading = $state(true);
  let filterStatus = $state('all');
  let deletingKey = $state('');

  $effect(() => {
    load();
  });

  async function load() {
    loading = true;
    try {
      const ap = activeProfile.current;
      const params: { profile_id?: number; status?: string } = {};
      if (ap) params.profile_id = ap.id;
      if (filterStatus !== 'all') params.status = filterStatus;
      const res = await listApplySessions({ ...params, limit: 100 });
      sessions = res.items;
      total = res.total;
    } catch {
      toastState.error('Failed to load sessions.');
    } finally {
      loading = false;
    }
  }

  async function remove(key: string) {
    deletingKey = key;
    try {
      await deleteApplySession(key);
      sessions = sessions.filter(s => s.session_key !== key);
      total -= 1;
    } catch {
      toastState.error('Failed to delete session.');
    } finally {
      deletingKey = '';
    }
  }

  // Stats
  const stats = $derived({
    total: sessions.length,
    completed: sessions.filter(s => s.status === 'completed').length,
    in_progress: sessions.filter(s => s.status === 'in_progress').length,
    partial: sessions.filter(s => s.status === 'partial').length,
    withCv: sessions.filter(s => s.generated_cv || (s.application_id && s.status === 'completed')).length,
  });

  const STATUS_STYLES: Record<string, string> = {
    completed:   'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    in_progress: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    partial:     'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
    abandoned:   'bg-muted text-muted-foreground',
  };

  const STATUS_LABELS: Record<string, string> = {
    completed:   'Completed',
    in_progress: 'In progress',
    partial:     'Partial',
    abandoned:   'Abandoned',
  };

  function scoreColor(score: number | null) {
    if (!score) return 'text-muted-foreground';
    if (score >= 75) return 'text-green-600 dark:text-green-400';
    if (score >= 50) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-500 dark:text-red-400';
  }

  function formatDate(iso: string) {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }
</script>

<div class="max-w-3xl space-y-6">
  <!-- Header -->
  <div class="flex items-start justify-between gap-4">
    <div>
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <BookOpen class="w-6 h-6 text-primary" />
        Apply Sessions
      </h1>
      <p class="text-sm text-muted-foreground mt-1">Every time you analyze a job via Add a Job, a session is saved here with a unique URL you can bookmark and return to.</p>
    </div>
    <a href="/smart-apply" class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-colors text-muted-foreground">
      <Zap class="w-3.5 h-3.5" />
      New session
    </a>
  </div>

  <!-- Stats row -->
  {#if !loading && sessions.length > 0}
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="rounded-lg border border-border bg-card p-4 text-center">
        <p class="text-2xl font-bold">{stats.total}</p>
        <p class="text-xs text-muted-foreground mt-0.5">Total sessions</p>
      </div>
      <div class="rounded-lg border border-border bg-card p-4 text-center">
        <p class="text-2xl font-bold text-green-600 dark:text-green-400">{stats.completed}</p>
        <p class="text-xs text-muted-foreground mt-0.5">Completed</p>
      </div>
      <div class="rounded-lg border border-border bg-card p-4 text-center">
        <p class="text-2xl font-bold text-blue-600 dark:text-blue-400">{stats.in_progress}</p>
        <p class="text-xs text-muted-foreground mt-0.5">In progress</p>
      </div>
      <div class="rounded-lg border border-border bg-card p-4 text-center">
        <p class="text-2xl font-bold text-yellow-600 dark:text-yellow-400">{stats.partial}</p>
        <p class="text-xs text-muted-foreground mt-0.5">Partial / failed</p>
      </div>
    </div>
  {/if}

  <!-- Filter bar -->
  <div class="flex items-center gap-2 flex-wrap">
    {#each [['all', 'All'], ['completed', 'Completed'], ['in_progress', 'In progress'], ['partial', 'Partial']] as [v, label]}
      <button
        onclick={() => { filterStatus = v; load(); }}
        class="px-3 py-1.5 rounded-md text-xs font-semibold border transition-all
          {filterStatus === v
            ? 'bg-primary text-primary-foreground border-primary'
            : 'bg-muted text-muted-foreground border-border hover:border-primary/30'}"
      >{label}</button>
    {/each}
    <span class="ml-auto text-xs text-muted-foreground">{total} session{total !== 1 ? 's' : ''}</span>
  </div>

  <!-- Session list -->
  {#if loading}
    <div class="space-y-3">
      {#each [1,2,3] as _}
        <div class="rounded-xl border border-border bg-card h-20 animate-pulse"></div>
      {/each}
    </div>
  {:else if sessions.length === 0}
    <div class="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <BookOpen class="w-10 h-10 text-muted-foreground/40" />
      <p class="text-sm font-medium text-muted-foreground">No sessions yet</p>
      <p class="text-xs text-muted-foreground/70">Start by analyzing a job in <a href="/smart-apply" class="underline text-primary">Add a Job</a>.</p>
    </div>
  {:else}
    <div class="space-y-3">
      {#each sessions as s}
        <div class="rounded-xl border border-border bg-card p-4 flex items-start gap-4 group hover:border-primary/30 transition-colors">
          <!-- Score badge -->
          <div class="w-12 h-12 rounded-lg border border-border bg-muted flex flex-col items-center justify-center shrink-0">
            {#if s.match_score !== null}
              <span class="text-base font-bold {scoreColor(s.match_score)}">{s.match_score}</span>
              <span class="text-[9px] text-muted-foreground">score</span>
            {:else}
              <Circle class="w-5 h-5 text-muted-foreground/40" />
            {/if}
          </div>

          <!-- Main info -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-semibold text-sm truncate">
                {s.role_title || 'Unknown role'}{s.company_name ? ` @ ${s.company_name}` : ''}
              </span>
              <span class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full {STATUS_STYLES[s.status] ?? 'bg-muted text-muted-foreground'}">
                {STATUS_LABELS[s.status] ?? s.status}
              </span>
            </div>

            <div class="flex items-center gap-3 mt-1 flex-wrap">
              {#if s.location}
                <span class="text-xs text-muted-foreground">{s.location}</span>
              {/if}
              {#if s.salary}
                <span class="text-xs text-muted-foreground">{s.salary}</span>
              {/if}
              <span class="text-xs text-muted-foreground">{formatDate(s.created_at)}</span>
            </div>

            <!-- Doc badges -->
            <div class="flex items-center gap-2 mt-2 flex-wrap">
              {#if s.application_id}
                <a href="/pipeline/{s.application_id}" class="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
                  <ExternalLink class="w-2.5 h-2.5" />
                  Pipeline
                </a>
              {/if}
              {#if s.status === 'completed' || s.generated_cv}
                <span class="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-green-500/10 text-green-700 dark:text-green-400">
                  <FileText class="w-2.5 h-2.5" />
                  CV generated
                </span>
              {/if}
              {#if s.status === 'completed' || s.generated_cl}
                <span class="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-700 dark:text-blue-400">
                  <FileText class="w-2.5 h-2.5" />
                  Cover letter
                </span>
              {/if}
              {#if s.config}
                {@const cfg = s.config as Record<string, unknown>}
                {#if cfg.language === 'fr'}
                  <span class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 font-medium">🇫🇷 FR</span>
                {/if}
              {/if}
              {#if s.job_url}
                <a href={s.job_url} target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors">
                  <ExternalLink class="w-2.5 h-2.5" />
                  Job posting
                </a>
              {/if}
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            <a
              href="/apply-sessions/{s.session_key}"
              class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-accent transition-colors"
            >
              <ExternalLink class="w-3 h-3" />
              View
            </a>
            <button
              onclick={() => remove(s.session_key)}
              disabled={deletingKey === s.session_key}
              class="p-1.5 rounded-md border border-border text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors disabled:opacity-50"
            >
              {#if deletingKey === s.session_key}
                <Loader2 class="w-3 h-3 animate-spin" />
              {:else}
                <Trash2 class="w-3 h-3" />
              {/if}
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
