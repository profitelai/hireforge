<script lang="ts">
  import { invalidateAll } from '$app/navigation';
  import { page } from '$app/state';
  import { activateProvider, connectLinkedIn, disconnectLinkedIn, disconnectProvider, fetchTTS, getIntegrations, getLinkedInStatus } from '$lib/api';
  import SettingsModal from '$lib/components/SettingsModal.svelte';
  import { toastState } from '$lib/toast.svelte';
  import type { IntegrationInfo } from '$lib/types';
  import { SPEED_PRESETS, VOICE_OPTIONS, voiceSettings } from '$lib/voiceSettings.svelte';
  import { CircleAlert, CircleCheck, Link, Mic, Pencil, Plus, Settings, Trash2, Volume2, Zap } from '@lucide/svelte';

  let modalOpen = $state(false);
  let modalProviderId = $state('');
  let modalModel = $state('');
  let modalApiKey = $state('');
  let integrations: IntegrationInfo[] = $state([]);
  let loading = $state(true);
  const isAdmin = $derived(auth.user?.id === 1);
  let activating = $state('');
  let confirmingActivate = $state('');
  let disconnecting = $state('');
  let confirmingDisconnect = $state('');

  const PROVIDER_COLORS: Record<string, string> = {
    gemini: '#8b5cf6',
    anthropic: '#f59e0b',
    openai: '#10b981',
    ollama: '#3b82f6',
  };

  const PROVIDER_ICONS: Record<string, string> = {
    gemini: '✦',
    anthropic: '◆',
    openai: '⬡',
    ollama: '⬢',
  };

  $effect(() => { loadIntegrations(); });

  async function loadIntegrations() {
    loading = true;
    try {
      const res = await getIntegrations();
      integrations = res.integrations;
    } finally {
      loading = false;
    }
  }

  function openEdit(integration: IntegrationInfo) {
    modalProviderId = integration.id;
    modalModel = integration.current_model ?? '';
    modalOpen = true;
    // Store apiKey for pre-filling in modal
    modalApiKey = integration.api_key ?? '';
  }

  async function handleActivate(providerId: string) {
    activating = providerId;
    try {
      await activateProvider(providerId);
      await invalidateAll();
      await loadIntegrations();
      toastState.success('Provider switched successfully.');
    } catch {
      toastState.error('Failed to switch provider.');
    } finally {
      activating = '';
      confirmingActivate = '';
    }
  }

  async function handleDisconnect(providerId: string) {
    disconnecting = providerId;
    try {
      const res = await disconnectProvider(providerId);
      integrations = res.integrations;
      await invalidateAll();
      toastState.success('Provider disconnected.');
    } catch {
      toastState.error('Failed to disconnect provider.');
    } finally {
      disconnecting = '';
      confirmingDisconnect = '';
    }
  }

  const anyConfigured = $derived(integrations.some((i) => i.api_key_configured));

  // LinkedIn session
  let linkedInConnected = $state(false);
  let linkedInLoading = $state(true);
  let liAtInput = $state('');
  let linkedInSaving = $state(false);
  let linkedInDisconnecting = $state(false);
  let showLiAtForm = $state(false);

  $effect(() => {
    getLinkedInStatus()
      .then(r => { linkedInConnected = r.connected; })
      .catch(() => {})
      .finally(() => { linkedInLoading = false; });
  });

  async function handleLinkedInConnect() {
    if (!liAtInput.trim()) return;
    linkedInSaving = true;
    try {
      await connectLinkedIn(liAtInput.trim());
      linkedInConnected = true;
      liAtInput = '';
      showLiAtForm = false;
      toastState.success('LinkedIn connected!');
    } catch {
      toastState.error('Failed to save LinkedIn session.');
    } finally {
      linkedInSaving = false;
    }
  }

  async function handleLinkedInDisconnect() {
    linkedInDisconnecting = true;
    try {
      await disconnectLinkedIn();
      linkedInConnected = false;
      toastState.success('LinkedIn disconnected.');
    } catch {
      toastState.error('Failed to disconnect LinkedIn.');
    } finally {
      linkedInDisconnecting = false;
    }
  }

  // Voice settings
  let testingVoice = $state(false);
  const TEST_PHRASES: Record<string, string> = {
    en: "Hello! I'm your AI interview coach. Let's practice together.",
    fr: "Bonjour ! Je suis votre coach d'entretien IA. Entraînons-nous ensemble.",
  };
  let testLang = $state<'en' | 'fr'>('en');

  async function testVoice() {
    testingVoice = true;
    try {
      const blob = await fetchTTS(TEST_PHRASES[testLang], voiceSettings.current.voice, voiceSettings.current.speed);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => { URL.revokeObjectURL(url); testingVoice = false; };
      audio.onerror = () => { URL.revokeObjectURL(url); testingVoice = false; };
      await audio.play();
    } catch (e) {
      toastState.error('Voice test failed — make sure OpenAI is configured.');
      testingVoice = false;
    }
  }
</script>

<div class="max-w-2xl space-y-6">
  <div class="flex items-start justify-between gap-4">
    <div>
    <h1 class="text-2xl font-bold flex items-center gap-2">
      <Settings class="w-6 h-6 text-primary" />
      Settings
    </h1>
    <p class="text-sm text-muted-foreground mt-1">Manage your AI integrations. You can connect multiple providers and switch between them.</p>
  </div>
    <a href="/usage" class="shrink-0 text-xs text-primary hover:underline mt-1">View LLM Usage →</a>
  </div>

  <!-- Active model status -->
  {#if !loading}
    {@const active = integrations.find((i) => i.is_active)}
    {#if active}
      <div class="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3">
        <div class="w-2 h-2 rounded-full bg-green-500 shrink-0 animate-pulse"></div>
        <div class="flex-1 min-w-0">
          <span class="text-xs text-muted-foreground">Active model</span>
          <p class="text-sm font-medium font-mono truncate">{active.current_model ?? active.label}</p>
        </div>
        <span class="text-xs text-muted-foreground">{active.label}</span>
      </div>
    {:else}
      <div class="flex items-center gap-3 rounded-lg border border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950/30 px-4 py-3">
        <CircleAlert class="w-4 h-4 text-yellow-500 shrink-0" />
        <p class="text-sm text-yellow-700 dark:text-yellow-400">No active model — configure a provider to enable AI features.</p>
      </div>
    {/if}
  {/if}

  <div class="space-y-3">
    <h2 class="text-sm font-medium text-muted-foreground uppercase tracking-wide">AI Integrations</h2>

    {#if loading}
      {#each [1, 2, 3, 4] as _}
        <div class="border border-border rounded-lg p-4 bg-card animate-pulse h-20"></div>
      {/each}
    {:else}
      {#each integrations as integration}
        {@const color = PROVIDER_COLORS[integration.id] ?? '#6b7280'}
        {@const icon = PROVIDER_ICONS[integration.id] ?? '◉'}
        <div class="border rounded-lg p-4 bg-card flex items-center gap-4 transition-colors {integration.is_active ? 'border-l-4 border-l-primary border-primary/20 bg-primary/5' : 'border-border'}">
          <!-- Icon -->
          <div class="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 text-base font-bold" style="background:{color}18; color:{color}">
            {icon}
          </div>

          <!-- Info -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-sm font-medium">{integration.label}</span>
              {#if integration.is_active}
                <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide" style="background:{color}20; color:{color}">
                  <Zap class="w-2.5 h-2.5" />
                  Active
                </span>
              {/if}
            </div>
            {#if integration.api_key_configured}
              <div class="flex items-center gap-1.5 mt-0.5">
                <CircleCheck class="w-3 h-3 text-green-500 shrink-0" />
                <span class="text-xs text-muted-foreground">
                  Connected
                  {#if integration.masked_api_key}
                    · <code class="text-xs bg-muted px-1 rounded">{integration.masked_api_key}</code>
                  {/if}
                </span>
              </div>
            {:else if integration.id === 'ollama'}
              <div class="flex items-center gap-1.5 mt-0.5">
                <span class="text-xs text-muted-foreground">Local · no API key needed</span>
              </div>
            {:else}
              <div class="flex items-center gap-1.5 mt-0.5">
                <CircleAlert class="w-3 h-3 text-muted-foreground/60 shrink-0" />
                <span class="text-xs text-muted-foreground">Not configured</span>
              </div>
            {/if}
            {#if integration.current_model}
              <p class="text-xs font-mono font-semibold text-foreground mt-0.5">
                {integration.current_model.split('/').pop()}
              </p>
            {/if}
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2 shrink-0">
            {#if isAdmin}
            {#if (integration.api_key_configured || integration.id === 'ollama') && !integration.is_active}
              {#if confirmingActivate === integration.id}
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-muted-foreground">Switch to {integration.label}?</span>
                  <button
                    onclick={async () => { await handleActivate(integration.id); }}
                    disabled={activating === integration.id}
                    class="px-2.5 py-1 rounded-md text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                  >Yes</button>
                  <button
                    onclick={() => confirmingActivate = ''}
                    class="px-2.5 py-1 rounded-md text-xs border border-border hover:bg-accent transition-colors"
                  >No</button>
                </div>
              {:else}
                <button
                  onclick={() => confirmingActivate = integration.id}
                  disabled={activating === integration.id}
                  class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border transition-colors disabled:opacity-50"
                  style="border-color:{color}50; color:{color}; background:{color}0a"
                >
                  <Zap class="w-3 h-3" />
                  Set Active
                </button>
              {/if}
            {/if}
            {#if integration.api_key_configured && !integration.is_active && integration.id !== 'ollama'}
              {#if confirmingDisconnect === integration.id}
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-muted-foreground">Remove key?</span>
                  <button
                    onclick={() => handleDisconnect(integration.id)}
                    disabled={disconnecting === integration.id}
                    class="px-2.5 py-1 rounded-md text-xs font-semibold bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50 transition-colors"
                  >Yes</button>
                  <button
                    onclick={() => confirmingDisconnect = ''}
                    class="px-2.5 py-1 rounded-md text-xs border border-border hover:bg-accent transition-colors"
                  >No</button>
                </div>
              {:else}
                <button
                  onclick={() => confirmingDisconnect = integration.id}
                  disabled={disconnecting === integration.id}
                  class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-border text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
                >
                  Remove
                </button>
              {/if}
            {/if}
            <button
              onclick={() => openEdit(integration)}
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm border border-border hover:bg-accent transition-colors text-muted-foreground"
            >
              {#if integration.api_key_configured || integration.id === 'ollama'}
                <Pencil class="w-3.5 h-3.5" />
                Edit
              {:else}
                <Plus class="w-3.5 h-3.5" />
                Connect
              {/if}
            </button>
            {:else}
              <span class="text-xs text-muted-foreground italic px-2">View only</span>
            {/if}
          </div>
        </div>
      {/each}

      {#if !anyConfigured}
        <p class="text-xs text-muted-foreground text-center py-2">
          Connect at least one provider to enable AI features.
        </p>
      {/if}
    {/if}
  </div>
</div>

<!-- ── LinkedIn Session ────────────────────────────────────────────────── -->
<div class="space-y-4 mt-8">
  <div class="flex items-center gap-2">
    <Link class="w-4 h-4 text-primary" />
    <h2 class="text-sm font-medium text-muted-foreground uppercase tracking-wide">LinkedIn Session</h2>
  </div>
  <p class="text-xs text-muted-foreground -mt-1">
    Required for scraping LinkedIn job URLs and auto-apply. Paste your <code class="bg-muted px-1 rounded text-[11px]">li_at</code> cookie from your browser.
  </p>

  {#if linkedInLoading}
    <div class="h-14 rounded-lg border bg-muted/30 animate-pulse"></div>
  {:else}
    <div class="flex items-center gap-4 rounded-lg border p-4 bg-card {linkedInConnected ? 'border-green-500/30 bg-green-500/5' : 'border-border'}">
      {#if linkedInConnected}
        <CircleCheck class="w-5 h-5 text-green-500 shrink-0" />
        <div class="flex-1">
          <p class="text-sm font-medium">Connected</p>
          <p class="text-xs text-muted-foreground">LinkedIn session is active — job URL scraping enabled.</p>
        </div>
        <button
          onclick={handleLinkedInDisconnect}
          disabled={linkedInDisconnecting}
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs border border-border text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors disabled:opacity-50"
        >
          <Trash2 class="w-3.5 h-3.5" />
          {linkedInDisconnecting ? 'Removing…' : 'Disconnect'}
        </button>
      {:else}
        <CircleAlert class="w-5 h-5 text-muted-foreground/60 shrink-0" />
        <div class="flex-1">
          <p class="text-sm font-medium">Not connected</p>
          <p class="text-xs text-muted-foreground">LinkedIn URL scraping and auto-apply require a session.</p>
        </div>
        <button
          onclick={() => showLiAtForm = !showLiAtForm}
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-primary/40 text-primary bg-primary/5 hover:bg-primary/10 transition-colors"
        >
          <Plus class="w-3.5 h-3.5" />
          Connect
        </button>
      {/if}
    </div>

    {#if showLiAtForm && !linkedInConnected}
      <div class="space-y-4 rounded-lg border bg-muted/30 p-4">
        <!-- Primary: run the local script -->
        <div class="space-y-2">
          <p class="text-xs font-semibold">Recommended — run the login script (captures full session):</p>
          <div class="flex items-center gap-2 bg-background border rounded-md px-3 py-2">
            <code class="text-xs flex-1 select-all">python3 ./scripts/linkedin_login.py</code>
          </div>
          <p class="text-[11px] text-muted-foreground">
            Opens a browser window → you log in → session is saved automatically. Then click <strong>Check connection</strong> below.
          </p>
          <button
            onclick={async () => { linkedInLoading = true; try { const r = await getLinkedInStatus(); linkedInConnected = r.connected; if (r.connected) { showLiAtForm = false; toastState.success('LinkedIn connected!'); } else { toastState.error('Not connected yet — run the script first.'); } } finally { linkedInLoading = false; } }}
            class="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-accent transition-colors"
          >Check connection</button>
        </div>

        <div class="flex items-center gap-2 text-[10px] text-muted-foreground">
          <div class="flex-1 border-t"></div>
          <span>or paste manually (less reliable)</span>
          <div class="flex-1 border-t"></div>
        </div>

        <!-- Fallback: manual li_at paste -->
        <div class="space-y-2">
          <p class="text-xs font-semibold">Manual — paste <code class="bg-muted px-1 rounded">li_at</code> cookie only:</p>
          <ol class="text-[11px] text-muted-foreground space-y-0.5 list-decimal list-inside">
            <li>Open <strong>linkedin.com</strong> and log in</li>
            <li>DevTools → Application → Cookies → <code class="bg-muted px-1 rounded">www.linkedin.com</code></li>
            <li>Find <code class="bg-muted px-1 rounded">li_at</code> and copy its value</li>
          </ol>
          <div class="flex gap-2">
            <input
              type="password"
              bind:value={liAtInput}
              placeholder="Paste li_at value…"
              class="flex-1 rounded-md border border-input bg-background px-3 py-2 text-xs ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              onclick={handleLinkedInConnect}
              disabled={linkedInSaving || !liAtInput.trim()}
              class="px-4 py-2 rounded-md text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {linkedInSaving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    {/if}
  {/if}
</div>

<!-- ── Voice Settings ──────────────────────────────────────────────────── -->
<div class="space-y-4 mt-8">
  <div class="flex items-center gap-2">
    <Volume2 class="w-4 h-4 text-primary" />
    <h2 class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Interview Voice</h2>
  </div>
  <p class="text-xs text-muted-foreground -mt-1">Choose how the AI coach speaks during interview practice. Works in English and French.</p>

  <!-- Voice picker -->
  <div class="space-y-2">
    <p class="text-xs font-semibold text-foreground">Voice</p>
    <div class="grid grid-cols-2 gap-2">
      {#each VOICE_OPTIONS as opt}
        <button
          onclick={() => voiceSettings.setVoice(opt.value)}
          class="flex flex-col items-start px-3 py-2.5 rounded-lg border text-left transition-all
            {voiceSettings.current.voice === opt.value
              ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
              : 'border-border bg-card hover:border-primary/30 hover:bg-muted/40'}"
        >
          <div class="flex items-center gap-2 w-full">
            <Mic class="w-3.5 h-3.5 {voiceSettings.current.voice === opt.value ? 'text-primary' : 'text-muted-foreground'} shrink-0" />
            <span class="text-sm font-semibold">{opt.label}</span>
            <span class="ml-auto text-[10px] font-medium px-1.5 py-0.5 rounded-full
              {opt.gender === 'Male' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' :
               opt.gender === 'Female' ? 'bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300' :
               'bg-muted text-muted-foreground'}">{opt.gender}</span>
          </div>
          <p class="text-[11px] text-muted-foreground mt-0.5 pl-5">{opt.description}</p>
        </button>
      {/each}
    </div>
  </div>

  <!-- Speed -->
  <div class="space-y-2">
    <p class="text-xs font-semibold text-foreground">Speed</p>
    <div class="flex gap-2">
      {#each SPEED_PRESETS as preset}
        <button
          onclick={() => voiceSettings.setSpeed(preset.value)}
          class="flex-1 py-2 rounded-lg border text-xs font-semibold transition-all
            {voiceSettings.current.speed === preset.value
              ? 'border-primary bg-primary/5 text-primary'
              : 'border-border bg-card text-muted-foreground hover:border-primary/30'}"
        >{preset.label}</button>
      {/each}
    </div>
    <p class="text-[11px] text-muted-foreground">Current: {voiceSettings.current.speed}×</p>
  </div>

  <!-- Test phrase language + test button -->
  <div class="flex items-center gap-3">
    <div class="flex gap-1">
      {#each [{ v: 'en', label: '🇬🇧 EN' }, { v: 'fr', label: '🇫🇷 FR' }] as lang}
        <button
          onclick={() => testLang = lang.v as 'en' | 'fr'}
          class="px-3 py-1 rounded-md text-xs font-semibold border transition-all
            {testLang === lang.v
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-muted text-muted-foreground border-border hover:border-primary/40'}"
        >{lang.label}</button>
      {/each}
    </div>
    <button
      onclick={testVoice}
      disabled={testingVoice}
      class="flex items-center gap-2 px-4 py-2 rounded-lg border border-border bg-card hover:bg-accent transition-colors text-sm font-medium disabled:opacity-50"
    >
      <Volume2 class="w-4 h-4 {testingVoice ? 'animate-pulse text-primary' : 'text-muted-foreground'}" />
      {testingVoice ? 'Playing…' : 'Test voice'}
    </button>
    <button
      onclick={() => voiceSettings.reset()}
      class="text-xs text-muted-foreground hover:text-foreground transition-colors underline ml-auto"
    >Reset to default</button>
  </div>
</div>

<SettingsModal bind:open={modalOpen} initialProviderId={modalProviderId} initialModel={modalModel} initialApiKey={modalApiKey} />
