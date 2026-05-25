<script lang="ts">
  import { activeProfile } from '$lib/activeProfile.svelte';
  import {
    deleteAutoApplySession,
    listAutoApplySessions,
    type AutoApplySessionEntry,
  } from '$lib/api';
  import { toastState as toast } from '$lib/toast.svelte';
  import {
    Bot,
    Briefcase,
    CheckCircle,
    ChevronRight,
    FileText,
    Loader2,
    MapPin,
    Plus,
    RefreshCw,
    Search,
    Trash2,
  } from '@lucide/svelte';

  // ── State ─────────────────────────────────────────────────────────────────
  let sessions      = $state<AutoApplySessionEntry[]>([]);
  let loading       = $state(false);
  let deletingId    = $state<string | null>(null);

  // Filters
  let filterKeyword = $state('');
  let filterStatus  = $state('all');

  // ── Load ──────────────────────────────────────────────────────────────────
  async function load() {
    const ap = activeProfile.current;
    loading = true;
    try {
      const res = await listAutoApplySessions({
        profile_id: ap?.id,
        keyword: filterKeyword.trim() || undefined,
        status: filterStatus !== 'all' ? filterStatus : undefined,
      });
      sessions = res.items;
    } catch (e: any) {
      toast.error(e.message ?? 'Failed to load sessions.');
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    activeProfile.current; // reactive on profile change
    load();
  });

  async function handleDelete(sid: string, e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Delete this session and all its jobs?')) return;
    deletingId = sid;
    try {
      await deleteAutoApplySession(sid);
      sessions = sessions.filter(s => s.session_id !== sid);
      toast.success('Session deleted.');
    } catch (e: any) {
      toast.error(e.message ?? 'Delete failed.');
    } finally {
      deletingId = null;
    }
  }

  // ── Derived stats ─────────────────────────────────────────────────────────
  const totalJobs      = $derived(sessions.reduce((a, s) => a + s.total_jobs, 0));
  const totalResumes   = $derived(sessions.reduce((a, s) => a + s.generated_resumes, 0));
  const totalApplied   = $derived(sessions.reduce((a, s) => a + s.applied_jobs, 0));

  function formatDate(iso: string) {
    const d = new Date(iso);
    const now = new Date();
    const diff = Math.floor((now.getTime() - d.getTime()) / 86400000);
    if (diff === 0) return 'Today';
    if (diff === 1) return 'Yesterday';
    if (diff < 7) return `${diff}d ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function progressPct(s: AutoApplySessionEntry) {
    if (!s.total_jobs) return 0;
    return Math.round((s.completed_jobs / s.total_jobs) * 100);
  }
</script>

<div class="max-w-5xl mx-auto space-y-6">

  <!-- Header -->
  <div class="flex items-center justify-between gap-4">
    <div class="flex items-center gap-3">
      <div class="p-2 rounded-lg bg-primary/10">
        <Bot class="w-6 h-6 text-primary" />
      </div>
      <div>
        <h1 class="text-2xl font-bold">Auto Apply</h1>
        <p class="text-sm text-muted-foreground">One workspace per search — keyword · city · date</p>
      </div>
    </div>
    <a
      href="/auto-apply/session/new"
      class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
    >
      <Plus class="w-4 h-4" /> New Session
    </a>
  </div>

  <!-- Global stats -->
  {#if sessions.length > 0}
    <div class="grid grid-cols-4 gap-3">
      {#each [
        ['Sessions', sessions.length, ''],
        ['Jobs scanned', totalJobs, 'text-blue-600 dark:text-blue-400'],
        ['Resumes built', totalResumes, 'text-purple-600 dark:text-purple-400'],
        ['Applied', totalApplied, 'text-emerald-600 dark:text-emerald-400'],
      ] as [label, val, cls]}
        <div class="rounded-lg border bg-card p-4 text-center">
          <div class={`text-2xl font-black ${cls}`}>{val}</div>
          <div class="text-xs text-muted-foreground mt-0.5">{label}</div>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Filters -->
  <div class="flex items-center gap-3 flex-wrap">
    <div class="relative flex-1 min-w-48">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <input
        type="text"
        bind:value={filterKeyword}
        onkeydown={(e) => e.key === 'Enter' && load()}
        placeholder="Search keyword or city..."
        class="w-full pl-9 pr-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
      />
    </div>

    <div class="flex items-center gap-1">
      {#each [['all', 'All'], ['active', 'Active'], ['archived', 'Archived']] as [v, lbl]}
        <button
          onclick={() => { filterStatus = v; load(); }}
          class="px-3 py-1.5 rounded-md text-xs font-medium border transition-colors
            {filterStatus === v ? 'bg-primary text-primary-foreground border-primary' : 'border-border hover:bg-accent'}"
        >{lbl}</button>
      {/each}
    </div>

    <button
      onclick={load}
      disabled={loading}
      class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border hover:bg-accent transition-colors"
    >
      <RefreshCw class={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
    </button>
  </div>

  <!-- Session table -->
  {#if loading && sessions.length === 0}
    <div class="flex items-center justify-center py-20 text-muted-foreground">
      <Loader2 class="w-5 h-5 animate-spin mr-2" /> Loading sessions...
    </div>

  {:else if sessions.length === 0}
    <div class="flex flex-col items-center justify-center py-20 text-center gap-4">
      <Bot class="w-14 h-14 opacity-20" />
      <div>
        <p class="font-semibold">No sessions yet</p>
        <p class="text-sm text-muted-foreground mt-1">Each LinkedIn search becomes its own isolated workspace.</p>
      </div>
      <a
        href="/auto-apply/session/new"
        class="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
      >
        <Plus class="w-4 h-4" /> Start your first session
      </a>
    </div>

  {:else}
    <!-- Table header -->
    <div class="rounded-xl border bg-card overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b bg-muted/40">
            <th class="text-left px-4 py-3 font-medium text-muted-foreground text-xs">Session</th>
            <th class="text-center px-3 py-3 font-medium text-muted-foreground text-xs">Jobs</th>
            <th class="text-center px-3 py-3 font-medium text-muted-foreground text-xs">CVs</th>
            <th class="text-center px-3 py-3 font-medium text-muted-foreground text-xs">Applied</th>
            <th class="text-center px-3 py-3 font-medium text-muted-foreground text-xs">Progress</th>
            <th class="text-right px-4 py-3 font-medium text-muted-foreground text-xs">Created</th>
            <th class="px-3 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          {#each sessions as s (s.session_id)}
            {@const pct = progressPct(s)}
            <tr
              class="group hover:bg-muted/30 transition-colors cursor-pointer"
              onclick={() => window.location.href = `/auto-apply/session/${s.session_id}`}
            >
              <!-- Session name + meta -->
              <td class="px-4 py-3">
                <div class="flex items-start gap-2.5">
                  <div class="mt-0.5 p-1.5 rounded bg-primary/10 shrink-0">
                    <Bot class="w-3.5 h-3.5 text-primary" />
                  </div>
                  <div class="min-w-0">
                    <p class="font-semibold text-sm leading-tight truncate max-w-xs">
                      {s.label ?? s.session_id}
                    </p>
                    <div class="flex items-center gap-2 mt-0.5 flex-wrap">
                      {#if s.search_keyword}
                        <span class="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Briefcase class="w-3 h-3" />{s.search_keyword}
                        </span>
                      {/if}
                      {#if s.location}
                        <span class="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <MapPin class="w-3 h-3" />{s.location}
                        </span>
                      {/if}
                    </div>
                  </div>
                </div>
              </td>

              <!-- Jobs -->
              <td class="px-3 py-3 text-center">
                <span class="font-semibold">{s.total_jobs}</span>
                {#if s.pending_jobs > 0}
                  <span class="text-[10px] text-yellow-600 dark:text-yellow-400 block">
                    {s.pending_jobs} active
                  </span>
                {/if}
              </td>

              <!-- CVs -->
              <td class="px-3 py-3 text-center">
                <span class="flex items-center justify-center gap-1 font-semibold {s.generated_resumes > 0 ? 'text-purple-600 dark:text-purple-400' : 'text-muted-foreground'}">
                  {#if s.generated_resumes > 0}<FileText class="w-3 h-3" />{/if}
                  {s.generated_resumes}
                </span>
              </td>

              <!-- Applied -->
              <td class="px-3 py-3 text-center">
                <span class="font-semibold {s.applied_jobs > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}">
                  {#if s.applied_jobs > 0}<CheckCircle class="w-3 h-3 inline mr-0.5" />{/if}
                  {s.applied_jobs}
                </span>
              </td>

              <!-- Progress bar -->
              <td class="px-3 py-3">
                <div class="flex items-center gap-2 min-w-[80px]">
                  <div class="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                    <div
                      class="h-full rounded-full transition-all {pct === 100 ? 'bg-emerald-500' : 'bg-primary'}"
                      style="width: {pct}%"
                    ></div>
                  </div>
                  <span class="text-[10px] text-muted-foreground whitespace-nowrap">{pct}%</span>
                </div>
              </td>

              <!-- Date -->
              <td class="px-4 py-3 text-right">
                <span class="text-xs text-muted-foreground">{formatDate(s.created_at)}</span>
              </td>

              <!-- Actions -->
              <td class="px-3 py-3">
                <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onclick={(e) => handleDelete(s.session_id, e)}
                    disabled={deletingId === s.session_id}
                    class="p-1.5 rounded text-muted-foreground hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                  >
                    {#if deletingId === s.session_id}
                      <Loader2 class="w-3.5 h-3.5 animate-spin" />
                    {:else}
                      <Trash2 class="w-3.5 h-3.5" />
                    {/if}
                  </button>
                  <ChevronRight class="w-4 h-4 text-muted-foreground" />
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
