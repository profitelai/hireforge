import { redirect, isRedirect } from '@sveltejs/kit';
import { browser } from '$app/environment';
import { getOnboardingStatus, getStatus, listProfiles, createProfile, authMe } from '$lib/api';
import { profiles } from '$lib/profiles.svelte';
import { activeProfile } from '$lib/activeProfile.svelte';

const TOKEN_KEY = 'hireforge_token';

let cachedOnboarded: boolean | null = null;
let cachedApiKeyConfigured: boolean | null = null;
let profilesLoaded = false;

export const ssr = false;

const AUTH_FREE = ['/login', '/register'];

export const load = async ({ url, fetch }) => {
  const pathname = url.pathname;

  // Allow login/register without auth
  if (AUTH_FREE.some(p => pathname.startsWith(p))) {
    return { isOnboarded: false, isApiKeyConfigured: true };
  }

  // Check auth token
  const token = browser ? localStorage.getItem(TOKEN_KEY) : null;
  if (!token) {
    throw redirect(307, '/login');
  }

  const onSettings = pathname.startsWith('/settings');
  const onOnboarding = pathname.startsWith('/onboarding');
  const onProfile = pathname === '/profile' || pathname.startsWith('/profile/');

  if (onSettings || onOnboarding) {
    cachedOnboarded = null;
    cachedApiKeyConfigured = null;
    profilesLoaded = false;
  }

  let isOnboarded = cachedOnboarded ?? true;
  let isApiKeyConfigured = cachedApiKeyConfigured ?? true;

  try {
    if (cachedOnboarded === null || cachedApiKeyConfigured === null) {
      const [onboarding, llmStatus] = await Promise.all([
        getOnboardingStatus(fetch),
        getStatus(fetch),
      ]);
      isOnboarded = onboarding.is_onboarded;
      isApiKeyConfigured = llmStatus.api_key_configured;
      cachedOnboarded = isOnboarded;
      cachedApiKeyConfigured = isApiKeyConfigured;
    }

    if (!profilesLoaded) {
      try {
        let res = await listProfiles(fetch);
        if (res.items.length === 0) {
          await createProfile({ label: 'Default', color: '#6366f1', icon: '💼' }, fetch);
          res = await listProfiles(fetch);
        }
        profiles.set(res.items);
        profilesLoaded = true;

        let storedId: number | null = null;
        if (browser) {
          try {
            const raw = localStorage.getItem('activeProfile');
            if (raw) storedId = JSON.parse(raw)?.id ?? null;
          } catch { /* ignore */ }
        }
        const activeItem =
          (storedId != null ? res.items.find((p) => p.id === storedId) : null) ??
          res.items[0] ?? null;
        const validated = activeItem
          ? { id: activeItem.id, label: activeItem.label, color: activeItem.color, icon: activeItem.icon, name: activeItem.name }
          : null;
        activeProfile.initFromStorage(validated);
      } catch (e) {
        console.warn('Could not load profiles.', e);
      }
    }

    if (!isApiKeyConfigured && !onSettings) {
      throw redirect(307, '/settings');
    }
    if (!isOnboarded && !onSettings && !onOnboarding && !onProfile) {
      throw redirect(307, '/onboarding');
    }
  } catch (err: unknown) {
    if (isRedirect(err)) throw err;
    // If API returns 401, clear token and redirect to login
    if (err instanceof Error && err.message.includes('401')) {
      if (browser) localStorage.removeItem(TOKEN_KEY);
      throw redirect(307, '/login');
    }
    console.warn('Could not check onboarding status.', err);
  }

  return { isOnboarded, isApiKeyConfigured };
};
