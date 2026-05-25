<script lang="ts">
  import { goto } from '$app/navigation';
  import { activeProfile } from '$lib/activeProfile.svelte';
  import { getLinkedInStatus, scanJobs } from '$lib/api';
  import { toastState as toast } from '$lib/toast.svelte';
  import {
    ArrowLeft,
    Bot,
    ClipboardCopy,
    Loader2,
    MapPin,
    Search,
    Wifi,
    WifiOff,
    RefreshCw,
  } from '@lucide/svelte';

  // ── LinkedIn status ───────────────────────────────────────────────────────
  let linkedinConnected = $state<boolean | null>(null);
  let linkedinAge       = $state<number | null>(null);
  let checkingLinkedIn  = $state(false);
  let copied            = $state(false);

  const CONNECT_CMD = 'python3 /Users/danimaster/applykit/linkedin_connect.py';

  async function checkLinkedIn() {
    checkingLinkedIn = true;
    try {
      const s = await getLinkedInStatus();
      linkedinConnected = s.connected;
      linkedinAge = (s as any).age_days ?? null;
    } catch { linkedinConnected = false; }
    finally { checkingLinkedIn = false; }
  }

  async function copyCmd() {
    await navigator.clipboard.writeText(CONNECT_CMD);
    copied = true;
    setTimeout(() => { copied = false; }, 2000);
  }

  $effect(() => { checkLinkedIn(); });

  // ── Form ──────────────────────────────────────────────────────────────────
  let keyword     = $state('');
  let location    = $state('');
  let maxJobs     = $state(50);
  let easyApply   = $state(false);
  let customUrl   = $state('');
  let showUrl     = $state(false);
  let scanning    = $state(false);

  const generatedUrl = $derived(() => {
    if (!keyword.trim() && !location.trim()) return '';
    const kw = encodeURIComponent(keyword.trim());
    const loc = encodeURIComponent(location.trim());
    const parts: string[] = [];
    if (kw) parts.push(`keywords=${kw}`);
    if (loc) parts.push(`location=${loc}`);
    if (easyApply) parts.push('f_LF=f_AL');
    return `https://www.linkedin.com/jobs/search/?${parts.join('&')}`;
  });

  const scanUrl = $derived(customUrl.trim() || generatedUrl());

  async function handleStart() {
    const ap = activeProfile.current;
    if (!ap) return toast.error('Select a profile first.');
    if (!keyword.trim() && !location.trim() && !customUrl.trim()) {
      return toast.error('Enter a job title or location to continue.');
    }

    scanning = true;
    try {
      const scan = await scanJobs({
        url: scanUrl,
        profile_id: ap.id,
        max_jobs: maxJobs,
        easy_apply_only: easyApply,
        search_keyword: keyword.trim() || undefined,
        location: location.trim() || undefined,
      });

      if (scan.scraped === 0) {
        toast.error('No jobs found. Check your LinkedIn session or try a different search.');
        scanning = false;
        return;
      }

      toast.success(`Found ${scan.scraped} jobs (${scan.created} new). Opening session…`);
      goto(`/auto-apply/session/${scan.session_id}`);
    } catch (e: any) {
      toast.error(e.message ?? 'Scan failed.');
      scanning = false;
    }
  }
</script>

<div class="max-w-2xl mx-auto space-y-6">

  <!-- Header -->
  <div class="flex items-center gap-3">
    <a href="/auto-apply" class="p-1.5 rounded-lg hover:bg-accent transition-colors text-muted-foreground hover:text-foreground">
      <ArrowLeft class="w-5 h-5" />
    </a>
    <div class="p-2 rounded-lg bg-primary/10">
      <Bot class="w-6 h-6 text-primary" />
    </div>
    <div>
      <h1 class="text-xl font-bold">New Auto Apply Session</h1>
      <p class="text-sm text-muted-foreground">Each session is isolated — its own jobs, resumes, and history</p>
    </div>
  </div>

  <div class="rounded-xl border bg-card p-6 space-y-5">

    <!-- LinkedIn status -->
    <div class={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm ${
      linkedinConnected === null ? 'bg-muted'
      : linkedinConnected ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
      : 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800'
    }`}>
      {#if checkingLinkedIn}
        <Loader2 class="w-4 h-4 animate-spin text-muted-foreground shrink-0" />
        <span class="text-muted-foreground text-xs">Checking LinkedIn…</span>
      {:else if linkedinConnected}
        <Wifi class="w-4 h-4 text-green-600 dark:text-green-400 shrink-0" />
        <span class="text-green-700 dark:text-green-300 text-xs flex-1">
          LinkedIn connected{linkedinAge !== null ? ` · ${linkedinAge}d old` : ''}
        </span>
        <button onclick={checkLinkedIn}><RefreshCw class="w-3.5 h-3.5 text-muted-foreground" /></button>
      {:else}
        <WifiOff class="w-4 h-4 text-yellow-600 dark:text-yellow-400 shrink-0" />
        <span class="text-yellow-700 dark:text-yellow-300 text-xs flex-1">LinkedIn not connected</span>
        <button onclick={checkLinkedIn}><RefreshCw class="w-3.5 h-3.5 text-muted-foreground" /></button>
      {/if}
    </div>

    {#if linkedinConnected === false}
      <div class="rounded-lg bg-muted p-3 space-y-2">
        <p class="text-xs font-medium">Run in Terminal to connect:</p>
        <div class="flex items-center gap-2">
          <code class="flex-1 text-xs bg-background rounded px-2 py-1.5 border font-mono overflow-x-auto whitespace-nowrap">{CONNECT_CMD}</code>
          <button onclick={copyCmd} class="shrink-0 flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border hover:bg-accent transition-colors">
            <ClipboardCopy class="w-3.5 h-3.5" />{copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
      </div>
    {/if}

    <!-- Job title -->
    <label class="flex flex-col gap-1.5">
      <span class="text-sm font-medium">Job title / keywords</span>
      <input
        type="text"
        bind:value={keyword}
        placeholder="e.g. SEO Director, Full Stack Engineer, Marketing Manager"
        class="px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
      />
    </label>

    <!-- Location -->
    <label class="flex flex-col gap-1.5">
      <span class="text-sm font-medium flex items-center gap-1.5">
        <MapPin class="w-3.5 h-3.5 text-muted-foreground" /> Location
      </span>
      <input
        type="text"
        bind:value={location}
        placeholder="e.g. Montreal, Toronto, Remote, United States"
        class="px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
      />
    </label>

    <!-- Options row -->
    <div class="flex items-end gap-4 flex-wrap">
      <label class="flex flex-col gap-1">
        <span class="text-muted-foreground text-xs">Max jobs</span>
        <input type="number" bind:value={maxJobs} min="5" max="200"
          class="px-2 py-1.5 rounded border bg-background text-sm w-24" />
      </label>
      <label class="flex items-center gap-2 pb-1 cursor-pointer">
        <input type="checkbox" bind:checked={easyApply} class="rounded" />
        <span class="text-sm">Easy Apply only</span>
      </label>
    </div>

    <!-- Generated URL preview -->
    {#if scanUrl && !showUrl}
      <div class="rounded-lg bg-muted/50 p-3 flex items-center justify-between gap-2">
        <p class="text-xs text-muted-foreground truncate flex-1">{scanUrl}</p>
        <button onclick={() => { customUrl = scanUrl; showUrl = true; }}
          class="text-xs text-muted-foreground hover:text-foreground shrink-0 underline">Edit URL</button>
      </div>
    {/if}

    {#if showUrl}
      <label class="flex flex-col gap-1.5">
        <span class="text-sm font-medium">LinkedIn search URL</span>
        <textarea
          bind:value={customUrl}
          rows={2}
          placeholder="https://www.linkedin.com/jobs/search/?keywords=..."
          class="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none font-mono"
        ></textarea>
        <button onclick={() => { customUrl = ''; showUrl = false; }}
          class="text-xs text-muted-foreground hover:text-foreground self-start underline">Use auto-generated URL</button>
      </label>
    {/if}

    {#if !showUrl && !keyword.trim() && !location.trim()}
      <button onclick={() => { showUrl = true; }}
        class="text-xs text-muted-foreground hover:text-foreground underline">
        Paste LinkedIn URL directly instead
      </button>
    {/if}

    <!-- Pipeline steps preview -->
    <div class="rounded-lg bg-muted/40 p-4 space-y-2">
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">What happens next</p>
      <div class="grid grid-cols-4 gap-2">
        {#each [
          ['1', 'Scan', 'Collect job URLs'],
          ['2', 'Score', 'ATS fit analysis'],
          ['3', 'Resume', 'Tailored per job'],
          ['4', 'Cover Letter', 'Personalised'],
        ] as [n, title, desc]}
          <div class="text-center space-y-1">
            <div class="w-7 h-7 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mx-auto">{n}</div>
            <p class="text-xs font-medium">{title}</p>
            <p class="text-[10px] text-muted-foreground">{desc}</p>
          </div>
        {/each}
      </div>
    </div>

    <button
      onclick={handleStart}
      disabled={scanning || (!keyword.trim() && !location.trim() && !customUrl.trim())}
      class="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 transition-colors"
    >
      {#if scanning}
        <Loader2 class="w-4 h-4 animate-spin" /> Scanning LinkedIn…
      {:else}
        <Search class="w-4 h-4" /> Start Session
      {/if}
    </button>
  </div>
</div>
