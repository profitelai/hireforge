<script lang="ts">
  import { page } from '$app/state';
  import ProfileSwitcher from '$lib/components/ProfileSwitcher.svelte';
  import SettingsButton from '$lib/components/SettingsButton.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import Toaster from '$lib/components/Toaster.svelte';
  import { themeState } from '$lib/theme.svelte';
  import {
    BriefcaseBusiness,
    Bot,
    FileText,
    History,
    Menu,
    Mic,
    Plus,
    X,
    Zap,
  } from '@lucide/svelte';
  import '../app.css';
  import { auth } from '$lib/auth.svelte';
  import { goto } from '$app/navigation';
  import { LogOut } from '@lucide/svelte';

  function logout() {
    auth.logout();
    goto('/login');
  }

  let { data, children } = $props();
  const isOnboarded = $derived(data.isOnboarded);
  let mobileMenuOpen = $state(false);

  type NavItem = {
    href: string;
    label: string;
    icon?: typeof FileText;
    badge?: string;
    primary?: boolean;
  };

  const navMain: NavItem[] = [
    { href: '/tracker',      label: 'Pipeline',       icon: BriefcaseBusiness },
    { href: '/history',      label: 'History',        icon: History            },
    { href: '/generate',     label: 'Resume',         icon: FileText           },
    { href: '/cover-letter', label: 'Cover Letter',   icon: FileText           },
    { href: '/interview',    label: 'Interview',      icon: Mic                },
    { href: '/auto-apply',     label: 'Auto Apply',     icon: Bot,      badge: 'AI' },
  ];

  function isActive(href: string) {
    return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
  }

  $effect(() => {
    page.url.pathname;
    mobileMenuOpen = false;
  });

  $effect(() => {
    const isDark = themeState.current === 'dark';
    document.documentElement.classList.toggle('dark', isDark);
    localStorage.setItem('theme', themeState.current);
  });
</script>

<!-- ─── Shell ──────────────────────────────────────────────────────────── -->
<div class="min-h-screen flex flex-col bg-[oklch(0.985_0.003_247)] dark:bg-background">

  <!-- ─── Header ─────────────────────────────────────────────────────────── -->
  <header class="sticky top-0 z-50 w-full
    bg-white/80 dark:bg-card/80
    backdrop-blur-xl
    border-b border-border/60
    shadow-[0_1px_0_0_oklch(0.91_0.01_260/60%)]">
    <div class="mx-auto max-w-6xl px-4 h-14 flex items-center justify-between gap-4">

      <!-- Logo -->
      <div class="flex items-center gap-5 min-w-0">
        <a
          href={isOnboarded ? '/' : '/onboarding'}
          class="flex items-center gap-2 shrink-0 group"
        >
          <!-- Icon mark -->
          <div class="w-7 h-7 rounded-lg brand-gradient-bg flex items-center justify-center shadow-sm
            group-hover:shadow-md transition-shadow duration-200">
            <Zap class="w-4 h-4 text-white" strokeWidth={2.5} />
          </div>
          <!-- Wordmark -->
          <span class="font-bold text-[17px] tracking-tight">
            <span class="brand-gradient">HireForge</span>
          </span>
        </a>

        {#if isOnboarded}
          <!-- Desktop nav -->
          <nav class="hidden md:flex items-center gap-0.5 ml-1">
            <!-- New Application CTA -->
            <a
              href="/smart-apply"
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold
                transition-all duration-150
                {isActive('/smart-apply')
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'bg-primary/10 text-primary hover:bg-primary/15'}"
            >
              <Plus class="w-3.5 h-3.5" strokeWidth={2.5} />
              New Job
            </a>

            <div class="w-px h-4 bg-border mx-2"></div>

            {#each navMain as item}
              <a
                href={item.href}
                class="relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium
                  transition-all duration-150
                  {isActive(item.href)
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
              >
                {#if item.icon}
                  <item.icon class="w-3.5 h-3.5 shrink-0" />
                {/if}
                {item.label}
                {#if item.badge}
                  <span class="text-[9px] font-bold leading-none px-1 py-0.5 rounded
                    bg-violet-100 dark:bg-violet-900/40
                    text-violet-600 dark:text-violet-400
                    tracking-wide">
                    {item.badge}
                  </span>
                {/if}
              </a>
            {/each}
          </nav>
        {/if}
      </div>

      <!-- Right controls -->
      <div class="flex items-center gap-2 shrink-0">
        {#if isOnboarded}
          <ProfileSwitcher />
          <ThemeToggle />
          <SettingsButton />
          <button
            onclick={logout}
            class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Sign out"
          >
            <LogOut class="w-4 h-4" />
          </button>
          <!-- Mobile hamburger -->
          <button
            onclick={() => (mobileMenuOpen = !mobileMenuOpen)}
            class="md:hidden w-8 h-8 flex items-center justify-center rounded-lg
              hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            aria-label="Toggle menu"
          >
            {#if mobileMenuOpen}
              <X class="w-4.5 h-4.5" />
            {:else}
              <Menu class="w-4.5 h-4.5" />
            {/if}
          </button>
        {/if}
      </div>
    </div>

    <!-- Mobile menu -->
    {#if isOnboarded && mobileMenuOpen}
      <div class="md:hidden border-t border-border/60 bg-white/95 dark:bg-card/95
        backdrop-blur-xl animate-in slide-in-from-top-2 duration-200">
        <nav class="mx-auto max-w-6xl p-3 space-y-0.5">
          <a
            href="/smart-apply"
            class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-semibold
              transition-colors
              {isActive('/smart-apply')
                ? 'bg-primary text-primary-foreground'
                : 'text-primary hover:bg-primary/10'}"
          >
            <Plus class="w-4 h-4" strokeWidth={2.5} />
            New Application
          </a>

          {#each navMain as item}
            <a
              href={item.href}
              class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium
                transition-colors
                {isActive(item.href)
                  ? 'bg-accent text-accent-foreground'
                  : 'text-foreground hover:bg-muted'}"
            >
              {#if item.icon}
                <item.icon class="w-4 h-4 shrink-0 text-muted-foreground" />
              {/if}
              {item.label}
              {#if item.badge}
                <span class="ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded
                  bg-violet-100 dark:bg-violet-900/40
                  text-violet-600 dark:text-violet-400 tracking-wide">
                  {item.badge}
                </span>
              {/if}
            </a>
          {/each}
        </nav>
      </div>
    {/if}
  </header>

  <!-- ─── Page content ────────────────────────────────────────────────────── -->
  <main class="flex-1 mx-auto w-full max-w-6xl px-4 py-8">
    {@render children()}
  </main>

  <Toaster />
</div>
