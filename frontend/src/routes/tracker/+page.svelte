<script lang="ts">
	import { page } from '$app/state';
	import {
	    createApplication,
	    generateCvFromJdPdf,
	    generateCvPdf,
	    getCvHistoryEntry,
	    listApplications,
	    updateApplication,
	} from '$lib/api';
	import type { ApplicationFilters } from '$lib/types';
	import { profiles } from '$lib/profiles.svelte';
	import { activeProfile } from '$lib/activeProfile.svelte';
	import ApplicationCard from '$lib/components/tracker/ApplicationCard.svelte';
	import DetailPanel from '$lib/components/tracker/DetailPanel.svelte';
	import { STATUS_CONFIG } from '$lib/constants';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { toastState } from '$lib/toast.svelte';
	import type { ApplicationEntry, ApplicationStatus, CreateApplicationRequest } from '$lib/types';
	import { errorMessage } from '$lib/utils';
	import { Briefcase, CircleAlert, Download, FileText, Link, Loader2, Plus } from '@lucide/svelte';
	import { goto } from '$app/navigation';
	import { scrapeAnalyze } from '$lib/api';
	import { dndzone } from 'svelte-dnd-action';
	import { flip } from 'svelte/animate';

	let apps = $state<ApplicationEntry[]>([]);
	let loading = $state(true);
	let loadError = $state('');
	let selectedApp = $state<ApplicationEntry | null>(null);

	// Read initial filter values from URL query params
	const _params = page.url.searchParams;
	let search = $state(_params.get('company') ?? _params.get('search') ?? '');
	let dateRange = $state('all');
	let matchFilter = $state('all');
	let filterProfileId = $state<number | undefined>(undefined);
	let searchTimer: ReturnType<typeof setTimeout>;

	// If ?apply_date=YYYY-MM-DD or ?date_from=YYYY-MM-DD, pre-set dateRange to 'custom'
	let customDateFrom = $state(_params.get('apply_date') ?? _params.get('date_from') ?? '');

	const allProfiles = $derived(profiles.all);

	let addingInColumn = $state<ApplicationStatus | null>(null);
	let newCompany = $state('');
	let newRole = $state('');
	let newDate = $state(new Date().toISOString().split('T')[0]);

	const COLUMNS: { status: ApplicationStatus; label: string; color: string }[] = [
		{ status: 'applied', label: STATUS_CONFIG.applied.label, color: 'text-muted-foreground' },
		{ status: 'interviewing', label: STATUS_CONFIG.interviewing.label, color: STATUS_CONFIG.interviewing.color },
		{ status: 'offer', label: STATUS_CONFIG.offer.label, color: STATUS_CONFIG.offer.color },
		{ status: 'rejected', label: STATUS_CONFIG.rejected.label, color: STATUS_CONFIG.rejected.color },
	];

  // --- Derived ---
  const filtersActive = $derived(search !== '' || dateRange !== 'all' || matchFilter !== 'all' || filterProfileId !== undefined || customDateFrom !== '');
  const colItems = $derived(
    Object.fromEntries(
      COLUMNS.map((c) => [c.status, apps.filter((a) => a.status === c.status)])
    ) as Record<ApplicationStatus, ApplicationEntry[]>
  );

  // --- Data loading ---
  async function load() {
    loading = true;
    loadError = '';
    try {
      const filters: ApplicationFilters = { sort: 'date_desc' };
      if (filterProfileId !== undefined) filters.profile_id = filterProfileId;
      if (search) filters.search = search;
      if (matchFilter === 'high') { filters.match_min = 70; }
      else if (matchFilter === 'medium') { filters.match_min = 40; filters.match_max = 69; }
      else if (matchFilter === 'low') { filters.match_max = 39; }

      const today = new Date();
      if (customDateFrom) {
        filters.date_from = customDateFrom;
      } else if (dateRange === 'week') {
        const d = new Date(today); d.setDate(d.getDate() - 7);
        filters.date_from = d.toISOString().split('T')[0];
      } else if (dateRange === 'month') {
        filters.date_from = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-01`;
      } else if (dateRange === '3months') {
        const d = new Date(today); d.setMonth(d.getMonth() - 3);
        filters.date_from = d.toISOString().split('T')[0];
      }

      const res = await listApplications(filters);
      apps = res.items;

      // Highlight newly created application if redirected from Smart Apply
      const newId = page.url.searchParams.get('new');
      if (newId) {
        const target = apps.find(a => a.id === Number(newId));
        if (target) selectedApp = target;
      }
    } catch (e: unknown) {
      loadError = errorMessage(e);
      toastState.error(loadError);
    } finally {
      loading = false;
    }
  }

  $effect(() => { load(); });

  function onSearchInput() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(load, 300);
  }

  // --- Drag and drop ---
  function handleDndConsider(status: ApplicationStatus, e: CustomEvent) {
    // Update local state optimistically during drag
    const updated = apps.filter((a) => a.status !== status);
    apps = [...updated, ...e.detail.items.map((i: ApplicationEntry) => ({ ...i, status }))];
  }

  async function handleDndFinalize(status: ApplicationStatus, e: CustomEvent) {
    const { items: newItems, info: { id: draggedId } } = e.detail;
    
    // Update local state
    const updated = apps.filter((a) => a.status !== status);
    apps = [...updated, ...newItems.map((i: ApplicationEntry) => ({ ...i, status }))];

    // Only update backend if the item was dropped into this column
    const isPresent = newItems.some((i: ApplicationEntry) => i.id === draggedId);
    if (isPresent) {
      try {
        await updateApplication(draggedId, { status });
      } catch (err: unknown) {
        toastState.error('Failed to update application. Please try again.');
        await load();
      }
    }
  }

  // --- Add application ---
  function startAdding(status: ApplicationStatus) {
    addingInColumn = status;
    newCompany = '';
    newRole = '';
    newDate = new Date().toISOString().split('T')[0];
  }

  async function submitAdd() {
    if (!newCompany.trim() || !addingInColumn) return;
    try {
      const req: CreateApplicationRequest = {
        company_name: newCompany.trim(),
        role_title: newRole.trim(),
        status: addingInColumn,
        applied_date: newDate || null,
      };
      const created = await createApplication(req);
      apps = [created, ...apps];
      addingInColumn = null;
    } catch (e: unknown) {
      toastState.error(errorMessage(e));
    }
  }

  // --- Detail panel ---
  function handleUpdate(updated: ApplicationEntry) {
    apps = apps.map((a) => (a.id === updated.id ? updated : a));
    selectedApp = updated;
  }

  function handleDelete(id: number) {
    apps = apps.filter((a) => a.id !== id);
    selectedApp = null;
  }

  // --- Generate CV from JD PDF ---
  let showJdPdfModal  = $state(false);
  let jdPdfFile       = $state<File | null>(null);
  let jdText          = $state('');
  let jdCompany       = $state('');
  let jdRole          = $state('');
  let jdLang          = $state<'en' | 'fr'>('en');
  let jdGenerating    = $state(false);
  let jdResult        = $state<{ cv_id: number; company_name: string; role_title: string; profile: any } | null>(null);

  const jdReady = $derived(!!jdPdfFile || jdText.trim().length >= 50);

  async function generateFromJdPdf() {
    const ap = activeProfile.current;
    if (!ap) return toastState.error('Select a profile first.');
    if (!jdReady) return toastState.error('Upload a PDF or paste at least 50 characters of job description.');
    jdGenerating = true;
    jdResult = null;
    try {
      const res = await generateCvFromJdPdf(ap.id, {
        file: jdPdfFile ?? undefined,
        jdText: jdText.trim() || undefined,
        companyName: jdCompany.trim() || undefined,
        roleTitle: jdRole.trim() || undefined,
        language: jdLang,
      });
      jdResult = res;
      toastState.success(`Resume generated for ${res.company_name}!`);
    } catch (e: any) {
      toastState.error(e.message ?? 'Generation failed.');
    } finally {
      jdGenerating = false;
    }
  }

  async function downloadJdCvPdf() {
    if (!jdResult) return;
    try {
      const blob = await generateCvPdf({ profile: jdResult.profile });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `resume-${jdResult.company_name.replace(/\s+/g, '-').toLowerCase()}.pdf`;
      a.click();
    } catch (e: any) { toastState.error('PDF download failed.'); }
  }

  function resetJdModal() {
    jdPdfFile = null; jdText = ''; jdCompany = ''; jdRole = ''; jdResult = null; jdGenerating = false; jdLang = 'en';
    showJdPdfModal = false;
  }

  // --- Add from URL ---
  let showUrlModal = $state(false);
  let urlInput = $state('');
  let urlScraping = $state(false);

  async function addFromUrl() {
    if (!urlInput.trim()) return;
    urlScraping = true;
    try {
      const result = await scrapeAnalyze({ url: urlInput.trim() });
      const created = await createApplication({
        company_name: result.company_name ?? 'Unknown Company',
        role_title: result.role_title ?? '',
        status: 'applied',
        job_url: urlInput.trim(),
        applied_date: new Date().toISOString().split('T')[0],
        job_description: result.job_description,
        location: result.location ?? undefined,
        salary: result.salary ?? undefined,
      });
      showUrlModal = false;
      urlInput = '';
      toastState.success(`Added: ${created.company_name}`);
      goto(`/pipeline/${created.id}`);
    } catch (e: unknown) {
      toastState.error(`Failed to add from URL: ${errorMessage(e)}`);
    } finally {
      urlScraping = false;
    }
  }
</script>

<svelte:head>
  <title>HireForge — Job Application Tracker</title>
  <meta name="description" content="Track all your job applications in one place. Monitor application status from applied to offer." />
</svelte:head>

<div class="space-y-4 transition-[padding-right] duration-200 {selectedApp ? 'md:pr-94' : ''}"
>
  <div class="flex items-center justify-between mt-2">
    <div>
      <h1 class="text-3xl font-black tracking-tight">Tracker</h1>
      <p class="text-sm text-muted-foreground">Manage and track your job applications in one place.</p>
    </div>
    <div class="flex items-center gap-2">
      <button
        onclick={() => showJdPdfModal = true}
        class="flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-bold hover:bg-accent transition-colors shrink-0"
      >
        <FileText class="w-3.5 h-3.5" />
        Resume from JD PDF
      </button>
      <button
        onclick={() => showUrlModal = true}
        class="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-colors shrink-0"
      >
        <Link class="w-3.5 h-3.5" />
        Add from URL
      </button>
    </div>
  </div>

  <!-- Add from URL modal -->
  {#if showUrlModal}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onclick={(e) => { if (e.target === e.currentTarget) showUrlModal = false; }}
      role="dialog"
      aria-modal="true"
      aria-label="Add job from URL"
    >
      <div class="bg-card rounded-xl border border-border shadow-xl w-full max-w-md p-6 space-y-4">
        <h2 class="text-base font-bold">Add Job from URL</h2>
        <p class="text-xs text-muted-foreground">Paste a LinkedIn, Greenhouse, Lever, or any job posting URL. We'll scrape the details automatically.</p>
        <input
          class="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm focus:ring-1 focus:ring-primary outline-none"
          placeholder="https://linkedin.com/jobs/view/..."
          bind:value={urlInput}
          onkeydown={(e) => { if (e.key === 'Enter') addFromUrl(); }}
          autofocus
        />
        <div class="flex gap-2">
          <button
            onclick={addFromUrl}
            disabled={urlScraping || !urlInput.trim()}
            class="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-bold disabled:opacity-50 hover:bg-primary/90 transition-colors"
          >
            {#if urlScraping}
              <div class="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
              Scraping...
            {:else}
              <Plus class="w-4 h-4" />
              Add & Open Pipeline
            {/if}
          </button>
          <button
            onclick={() => showUrlModal = false}
            class="px-4 py-2.5 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Generate Resume from JD modal -->
  {#if showJdPdfModal}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onclick={(e) => { if (e.target === e.currentTarget) resetJdModal(); }}
      role="dialog" aria-modal="true">
      <div class="bg-card rounded-xl border shadow-xl w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-bold">Generate Resume from Job Description</h2>
          <!-- Language toggle -->
          <div class="flex items-center gap-1 rounded-lg border p-0.5 text-xs font-medium">
            {#each [['en', 'English'], ['fr', 'Français']] as [val, label]}
              <button onclick={() => jdLang = val as 'en' | 'fr'}
                class="px-2.5 py-1 rounded-md transition-colors {jdLang === val ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}">
                {label}
              </button>
            {/each}
          </div>
        </div>
        <p class="text-xs text-muted-foreground">Upload a PDF <em>or</em> paste the job description text — we'll tailor your resume to it and save to History.</p>

        <!-- PDF upload -->
        <label class="flex flex-col gap-1.5">
          <span class="text-sm font-medium">Upload PDF <span class="text-muted-foreground text-xs">(optional if pasting text)</span></span>
          <input type="file" accept=".pdf"
            onchange={(e) => { jdPdfFile = (e.target as HTMLInputElement).files?.[0] ?? null; }}
            class="text-sm file:mr-3 file:py-1 file:px-3 file:rounded file:border file:text-xs file:font-medium file:bg-muted file:cursor-pointer" />
          {#if jdPdfFile}<p class="text-xs text-emerald-600">{jdPdfFile.name} ✓</p>{/if}
        </label>

        <!-- Paste text -->
        <label class="flex flex-col gap-1.5">
          <span class="text-sm font-medium">Or paste job description text <span class="text-muted-foreground text-xs">(optional if uploading PDF)</span></span>
          <textarea bind:value={jdText} rows={5}
            placeholder="Paste the full job description here…"
            class="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y font-mono text-xs">
          </textarea>
          {#if jdText.trim().length > 0 && jdText.trim().length < 50}
            <p class="text-xs text-yellow-600">Need at least 50 characters ({jdText.trim().length}/50)</p>
          {/if}
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="flex flex-col gap-1.5">
            <span class="text-sm font-medium">Company Name <span class="text-muted-foreground text-xs">(optional)</span></span>
            <input type="text" bind:value={jdCompany} placeholder="e.g. Google"
              class="px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50" />
          </label>
          <label class="flex flex-col gap-1.5">
            <span class="text-sm font-medium">Role Title <span class="text-muted-foreground text-xs">(optional)</span></span>
            <input type="text" bind:value={jdRole} placeholder="e.g. SEO Director"
              class="px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50" />
          </label>
        </div>

        {#if jdResult}
          <div class="rounded-lg bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 p-3 space-y-2">
            <p class="text-sm font-semibold text-emerald-700 dark:text-emerald-300">Resume ready — {jdResult.company_name} · {jdResult.role_title}</p>
            <div class="flex gap-2">
              <button onclick={downloadJdCvPdf}
                class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors">
                <Download class="w-3.5 h-3.5" /> Download Resume PDF
              </button>
              <a href="/history" class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground underline self-center">
                View in History
              </a>
            </div>
          </div>
        {/if}

        <div class="flex gap-2 pt-1">
          <button onclick={generateFromJdPdf} disabled={jdGenerating || !jdReady}
            class="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors">
            {#if jdGenerating}<Loader2 class="w-4 h-4 animate-spin" /> Generating resume…
            {:else}<FileText class="w-4 h-4" /> Generate Resume ({jdLang === 'fr' ? 'Français' : 'English'}){/if}
          </button>
          <button onclick={resetJdModal} class="px-4 py-2 rounded-lg border text-sm hover:bg-accent transition-colors">Close</button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Profile filter pills -->
  {#if allProfiles.length > 1}
    <div class="flex items-center gap-2 flex-wrap">
      <span class="text-xs text-muted-foreground uppercase tracking-wider">Profile:</span>
      <button
        onclick={() => { filterProfileId = undefined; load(); }}
        class="px-3 py-1 rounded-full text-xs font-medium border transition-colors
          {filterProfileId === undefined ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent'}"
      >All</button>
      {#each allProfiles as p}
        <button
          onclick={() => { filterProfileId = p.id; load(); }}
          class="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-colors
            {filterProfileId === p.id ? 'text-white border-transparent' : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent'}"
          style={filterProfileId === p.id ? `background:${p.color}; border-color:${p.color}` : ''}
        >
          <span class="w-1.5 h-1.5 rounded-full" style="background:{filterProfileId === p.id ? 'white' : p.color}"></span>
          {p.icon} {p.label}
        </button>
      {/each}
    </div>
  {/if}

  <!-- Filter bar -->
  <div class="flex items-center gap-3 flex-wrap">
    <input
      class="flex-1 min-w-50 bg-card border border-border rounded-md px-3 py-2 text-sm"
      placeholder="🔍 Search company or role..."
      bind:value={search}
      oninput={onSearchInput}
    />
    <select
      class="bg-card border border-border rounded-md px-3 py-2 text-sm"
      bind:value={dateRange}
      onchange={load}
    >
      <option value="all">All time</option>
      <option value="week">This week</option>
      <option value="month">This month</option>
      <option value="3months">Last 3 months</option>
    </select>
    <select
      class="bg-card border border-border rounded-md px-3 py-2 text-sm"
      bind:value={matchFilter}
      onchange={load}
    >
      <option value="all">All matches</option>
      <option value="high">High (≥70%)</option>
      <option value="medium">Medium (40–69%)</option>
      <option value="low">Low (&lt;40%)</option>
    </select>

    {#if customDateFrom}
      <span class="flex items-center gap-1 text-xs bg-muted border border-border rounded px-2 py-1 text-muted-foreground">
        From {customDateFrom}
        <button onclick={() => { customDateFrom = ''; load(); }} class="hover:text-foreground ml-0.5">×</button>
      </span>
    {/if}

    {#if filtersActive}
      <button
        onclick={() => { search = ''; dateRange = 'all'; matchFilter = 'all'; filterProfileId = undefined; customDateFrom = ''; load(); }}
        class="text-xs text-primary font-bold px-2 py-1 hover:bg-primary/5 rounded-md transition-colors"
      >
        ✕ Clear filters
      </button>
    {/if}
  </div>

  {#if loading}
    <div class="grid grid-cols-4 gap-4">
      {#each COLUMNS as _}
        <div class="bg-card border border-border rounded-xl p-3 h-64 animate-pulse"></div>
      {/each}
    </div>
  {:else if loadError}
    <div class="flex flex-col items-center justify-center py-20 text-center gap-3">
      <CircleAlert class="w-8 h-8 text-destructive" />
      <p class="text-sm font-medium text-destructive">Failed to load applications</p>
      <p class="text-xs text-muted-foreground">{loadError}</p>
      <button onclick={load} class="text-xs text-primary hover:underline mt-1">Try again</button>
    </div>
  {:else if filtersActive && apps.length === 0}
    <div class="flex flex-col items-center justify-center py-20 text-center gap-3">
      <p class="text-sm font-medium text-muted-foreground">No applications match your filters</p>
      <button
        onclick={() => { search = ''; dateRange = 'all'; matchFilter = 'all'; filterProfileId = undefined; customDateFrom = ''; load(); }}
        class="text-xs text-primary hover:underline"
      >Clear filters</button>
    </div>
  {:else}
    <!-- Kanban board -->
    <div class="grid grid-cols-4 gap-4 items-start">
      {#each COLUMNS as col}
        {@const items = colItems[col.status] ?? []}
        <div class="bg-card border border-border rounded-xl p-3 flex flex-col">
          <!-- Column header (sticky) -->
          <div class="sticky top-0 bg-card/95 backdrop-blur-sm z-10 flex items-center justify-between mb-3 py-1 border-b border-border/40">
            <span class="text-[10px] font-black uppercase tracking-widest {col.color}">{col.label}</span>
            <span class="text-[10px] font-bold text-muted-foreground bg-muted/50 rounded-full px-2 py-0.5 border border-border/40">{items.length}</span>
          </div>

          <!-- Cards (dnd zone) -->
          <div class="relative flex-1 flex flex-col min-h-32 mt-2">
            {#if items.length === 0}
              <div class="absolute inset-0 flex flex-col items-center justify-center py-8 text-center pointer-events-none opacity-40">
                <EmptyState
                  icon={Briefcase}
                  title="Empty"
                  description="Drop here"
                />
              </div>
            {/if}

            <div
              class="flex-1 flex flex-col gap-2 max-h-[60vh] overflow-y-auto pb-4"
              use:dndzone={{ items, flipDurationMs: 150, type: 'applications' }}
              onconsider={(e) => handleDndConsider(col.status, e)}
              onfinalize={(e) => handleDndFinalize(col.status, e)}
            >
              {#each items as app (app.id)}
                <div animate:flip={{ duration: 150 }}>
                  <ApplicationCard {app} onclick={() => (selectedApp = app)} />
                </div>
              {/each}
            </div>
          </div>

          <!-- Add form or button -->
          {#if addingInColumn === col.status}
            <form
              class="mt-3 space-y-2 border-t border-border pt-3"
              onsubmit={(e) => { e.preventDefault(); submitAdd(); }}
            >
              <input
                class="w-full bg-background border border-border rounded px-2 py-1.5 text-sm"
                placeholder="Company name *"
                bind:value={newCompany}
                required
              />
              <input
                class="w-full bg-background border border-border rounded px-2 py-1.5 text-sm"
                placeholder="Role title"
                bind:value={newRole}
              />
              <input
                type="date"
                class="w-full bg-background border border-border rounded px-2 py-1.5 text-sm"
                bind:value={newDate}
              />
              <div class="flex gap-2">
                <button
                  type="button"
                  onclick={() => (addingInColumn = null)}
                  class="flex-1 border border-border text-xs py-1.5 rounded hover:bg-accent"
                >Cancel</button>
                <button
                  type="submit"
                  class="flex-1 bg-primary text-primary-foreground text-xs py-1.5 rounded hover:bg-primary/90"
                >Add →</button>
              </div>
            </form>
          {:else}
            <button
              type="button"
              onclick={() => startAdding(col.status)}
              class="mt-3 w-full border border-dashed border-border rounded-md py-2 text-xs text-muted-foreground hover:text-foreground hover:border-muted-foreground transition-colors"
            >+ Add application</button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Detail panel -->
{#if selectedApp}
  <DetailPanel
    app={selectedApp}
    onclose={() => (selectedApp = null)}
    onupdate={handleUpdate}
    ondelete={handleDelete}
  />
{/if}
