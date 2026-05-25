<script lang="ts">
  import { goto } from '$app/navigation';
  import { authLogin } from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import { Button } from '$lib/components/ui/button';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Zap } from '@lucide/svelte';

  let email = $state('');
  let password = $state('');
  let error = $state('');
  let loading = $state(false);

  async function handleLogin(e: Event) {
    e.preventDefault();
    error = '';
    loading = true;
    try {
      const res = await authLogin({ email, password });
      auth.login(res.access_token, res.user);
      goto('/');
    } catch (err: unknown) {
      error = err instanceof Error ? err.message : 'Login failed. Check your credentials.';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Sign In — HireForge</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center bg-background px-4">
  <div class="w-full max-w-sm">
    <!-- Logo -->
    <div class="flex flex-col items-center mb-8">
      <div class="w-10 h-10 rounded-xl brand-gradient-bg flex items-center justify-center shadow-md mb-3">
        <Zap class="w-5 h-5 text-white" strokeWidth={2.5} />
      </div>
      <h1 class="text-2xl font-black tracking-tight"><span class="brand-gradient">HireForge</span></h1>
      <p class="text-sm text-muted-foreground mt-1">Sign in to your workspace</p>
    </div>

    <!-- Form -->
    <form onsubmit={handleLogin} class="space-y-4 bg-card border border-border rounded-2xl p-6 shadow-sm">
      <div class="space-y-1.5">
        <Label for="email">Email</Label>
        <Input id="email" type="email" bind:value={email} placeholder="you@example.com" required autocomplete="email" />
      </div>
      <div class="space-y-1.5">
        <Label for="password">Password</Label>
        <Input id="password" type="password" bind:value={password} placeholder="••••••••" required autocomplete="current-password" />
      </div>

      {#if error}
        <p class="text-sm text-red-500 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">{error}</p>
      {/if}

      <Button type="submit" class="w-full rounded-xl" disabled={loading}>
        {loading ? 'Signing in...' : 'Sign In'}
      </Button>
    </form>

    <p class="text-center text-sm text-muted-foreground mt-4">
      Don't have an account?
      <a href="/register" class="text-primary font-semibold hover:underline">Create one</a>
    </p>
    <p class="text-center text-xs text-muted-foreground mt-2">
      Get your account at
      <a href="https://hire.bizlocal.ca" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">hire.bizlocal.ca</a>
    </p>
  </div>
</div>
