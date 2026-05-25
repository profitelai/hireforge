<script lang="ts">
  import { activeProfile } from '$lib/activeProfile.svelte';
  import { deleteInterviewSession, listInterviewSessions } from '$lib/api';
  import { toastState } from '$lib/toast.svelte';
  import type { InterviewSessionSummary } from '$lib/types';
  import {
    ArrowLeft,
    BarChart3,
    BookOpen,
    Circle,
    ExternalLink,
    History,
    Loader2,
    Mic,
    Trash2,
    TrendingUp,
  } from '@lucide/svelte';

  let sessions = $state<InterviewSessionSummary[]>([]);
  let total = $state(0);
  let loading = $state(true);
  let filterLang = $state('all');
  let deletingId = $state<number | null>(null);

  $effect(() => {
    load();
  });

  async function load() {
    loading = true;
    try {
      const ap = activeProfile.current;
      const res = await listInterviewSessions({ profile_id: ap?.id, limit: 100 });
      sessions = res.items;
      total = res.total;
    } catch {
      toastState.error('Failed to load sessions.');
    } finally {
      loading = false;
    }
  }

  async function remove(id: number) {
    deletingId = id;
    try {
      await deleteInterviewSession(id);
      sessions = sessions.filter(s => s.id !== id);
      total -= 1;
      toastState.success('Session deleted.');
    } catch {
      toastState.error('Failed to delete session.');
    } finally {
      deletingId = null;
    }
  }

  const filtered = $derived(
    filterLang === 'all' ? sessions : sessions.filter(s => s.language === filterLang)
  );

  // Stats
  const stats = $derived({
    total: sessions.length,
    withScore: sessions.filter(s => s.overall_score !== null).length,
    avgScore: sessions.filter(s => s.overall_score !== null).length
      ? Math.round(sessions.filter(s => s.overall_score !== null).reduce((a, s) => a + (s.overall_score ?? 0), 0) / sessions.filter(s => s.overall_score !== null).length)
      : null,
    bestScore: sessions.filter(s => s.overall_score !== null).length
      ? Math.max(...sessions.filter(s => s.overall_score !== null).map(s => s.overall_score ?? 0))
      : null,
    fr: sessions.filter(s => s.language === 'FR').length,
  });

  // Score trend (last 10 completed sessions)
  const scoreTrend = $derived(
    sessions
      .filter(s => s.overall_score !== null)
      .slice(0, 10)
      .reverse()
      .map(s => s.overall_score ?? 0)
  );

  function scoreColor(score: number | null) {
    if (!score) return 'text-muted-foreground';
    if (score >= 80) return 'text-green-600 dark:text-green-400';
    if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-500 dark:text-red-400';
  }

  function scoreBg(score: number | null) {
    if (!score) return 'bg-muted/50 border-border';
    if (score >= 80) return 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800';
    if (score >= 60) return 'bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800';
    return 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800';
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function formatTime(iso: string) {
    return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }

  const LENGTH_LABELS: Record<string, string> = {
    short: 'Short',
    medium: 'Medium',
    detailed: 'Detailed',
  };
</script>

<div class="max-w-3xl space-y-6">
  <!-- Header -->
  <div class="flex items-start justify-between gap-4">
    <div>
      <div class="flex items-center gap-2 mb-1">
        <a href="/interview" class="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft class="w-4 h-4" />
          Interview Practice
        </a>
      </div>
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <History class="w-6 h-6 text-primary" />
        Session History
      </h1>
      <p class="text-sm text-muted-foreground mt-1">All your past interview practice sessions with scores, recordings, and full Q&A.</p>
    </div>
    <a href="/interview" class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-colors text-muted-foreground">
      <Mic class="w-3.5 h-3.5" />
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
        <p class="text-2xl font-bold {scoreColor(stats.avgScore)}">{stats.avgScore ?? '—'}{stats.avgScore ? '/100' : ''}</p>
        <p class="text-xs text-muted-foreground mt-0.5">Avg. score</p>
      </div>
      <div class="rounded-lg border border-border bg-card p-4 text-center">
        <p class="text-2xl font-bold text-green-600 dark:text-green-400">{stats.bestScore ?? '—'}{stats.bestScore ? '/100' : ''}</p>
        <p class="text-xs text-muted-foreground mt-0.5">Best score</p>
      </div>
      <div class="rounded-lg border border-border bg-card p-4 text-center">
        <p class="text-2xl font-bold text-indigo-600 dark:text-indigo-400">{stats.fr}</p>
        <p class="text-xs text-muted-foreground mt-0.5">French sessions</p>
      </div>
    </div>

    <!-- Score trend mini chart -->
    {#if scoreTrend.length >= 3}
      <div class="rounded-xl border border-border bg-card p-4 space-y-2">
        <div class="flex items-center gap-2">
          <TrendingUp class="w-4 h-4 text-primary" />
          <span class="text-sm font-semibold">Score trend (last {scoreTrend.length} sessions)</span>
        </div>
        <div class="flex items-end gap-1.5 h-12">
          {#each scoreTrend as score, i}
            <div class="flex-1 flex flex-col items-center gap-0.5">
              <div
                class="w-full rounded-sm {score >= 80 ? 'bg-green-400' : score >= 60 ? 'bg-yellow-400' : 'bg-red-400'}"
                style="height: {Math.max(4, (score / 100) * 40)}px"
              ></div>
              <span class="text-[9px] text-muted-foreground">{score}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {/if}

  <!-- Filter bar -->
  <div class="flex items-center gap-2 flex-wrap">
    {#each [['all', 'All'], ['EN', '🇬🇧 English'], ['FR', '🇫🇷 French']] as [v, label]}
      <button
        onclick={() => filterLang = v}
        class="px-3 py-1.5 rounded-md text-xs font-semibold border transition-all
          {filterLang === v
            ? 'bg-primary text-primary-foreground border-primary'
            : 'bg-muted text-muted-foreground border-border hover:border-primary/30'}"
      >{label}</button>
    {/each}
    <span class="ml-auto text-xs text-muted-foreground">{filtered.length} session{filtered.length !== 1 ? 's' : ''}</span>
  </div>

  <!-- Session list -->
  {#if loading}
    <div class="space-y-3">
      {#each [1,2,3,4] as _}
        <div class="rounded-xl border border-border bg-card h-20 animate-pulse"></div>
      {/each}
    </div>
  {:else if filtered.length === 0}
    <div class="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <BookOpen class="w-10 h-10 text-muted-foreground/40" />
      <p class="text-sm font-medium text-muted-foreground">No sessions yet</p>
      <p class="text-xs text-muted-foreground/70">Start an interview at <a href="/interview" class="underline text-primary">Interview Practice</a>.</p>
    </div>
  {:else}
    <div class="space-y-3">
      {#each filtered as s}
        <div class="rounded-xl border border-border bg-card flex items-stretch group hover:border-primary/30 transition-colors overflow-hidden">
          <!-- Score bar -->
          <div class="w-1.5 shrink-0 {s.overall_score !== null
            ? s.overall_score >= 80 ? 'bg-green-400' : s.overall_score >= 60 ? 'bg-yellow-400' : 'bg-red-400'
            : 'bg-muted'}">
          </div>

          <div class="flex items-center gap-4 p-4 flex-1 min-w-0">
            <!-- Score circle -->
            <div class="w-12 h-12 rounded-full border-2 flex flex-col items-center justify-center shrink-0
              {s.overall_score !== null
                ? s.overall_score >= 80 ? 'border-green-400' : s.overall_score >= 60 ? 'border-yellow-400' : 'border-red-400'
                : 'border-border'}">
              {#if s.overall_score !== null}
                <span class="text-base font-bold leading-none {scoreColor(s.overall_score)}">{s.overall_score}</span>
                <span class="text-[9px] text-muted-foreground leading-none">/100</span>
              {:else}
                <Circle class="w-4 h-4 text-muted-foreground/40" />
              {/if}
            </div>

            <!-- Info -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-sm font-semibold">{formatDate(s.created_at)}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full font-semibold
                  {s.language === 'FR'
                    ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300'
                    : 'bg-muted text-muted-foreground'}">{s.language === 'FR' ? '🇫🇷 FR' : '🇬🇧 EN'}</span>
                {#if s.answer_length && s.answer_length !== 'medium'}
                  <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">{LENGTH_LABELS[s.answer_length] ?? s.answer_length}</span>
                {/if}
              </div>
              <p class="text-xs text-muted-foreground mt-0.5">
                {s.question_count} question{s.question_count !== 1 ? 's' : ''} · {formatTime(s.created_at)}
                {#if s.overall_score === null}
                  · <span class="text-yellow-600 dark:text-yellow-400">no score</span>
                {/if}
              </p>
            </div>

            <!-- Actions -->
            <div class="flex items-center gap-2 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
              <a
                href="/interview/sessions/{s.id}"
                class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-accent transition-colors"
              >
                <ExternalLink class="w-3 h-3" />
                View
              </a>
              <button
                onclick={() => remove(s.id)}
                disabled={deletingId === s.id}
                class="p-1.5 rounded-md border border-border text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors disabled:opacity-50"
              >
                {#if deletingId === s.id}
                  <Loader2 class="w-3 h-3 animate-spin" />
                {:else}
                  <Trash2 class="w-3 h-3" />
                {/if}
              </button>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
