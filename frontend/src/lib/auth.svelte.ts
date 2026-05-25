import { browser } from '$app/environment';

const TOKEN_KEY = 'hireforge_token';
const USER_KEY = 'hireforge_user';

interface AuthUser {
  id: number;
  email: string;
  name: string;
}

function createAuthStore() {
  let token = $state<string | null>(browser ? localStorage.getItem(TOKEN_KEY) : null);
  let user = $state<AuthUser | null>((() => {
    if (!browser) return null;
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch { return null; }
  })());

  return {
    get token() { return token; },
    get user() { return user; },
    get isAuthenticated() { return token !== null; },

    login(newToken: string, newUser: AuthUser) {
      token = newToken;
      user = newUser;
      if (browser) {
        localStorage.setItem(TOKEN_KEY, newToken);
        localStorage.setItem(USER_KEY, JSON.stringify(newUser));
      }
    },

    logout() {
      token = null;
      user = null;
      if (browser) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
      }
    },
  };
}

export const auth = createAuthStore();

export function getAuthHeader(): Record<string, string> {
  const t = browser ? localStorage.getItem(TOKEN_KEY) : null;
  return t ? { Authorization: `Bearer ${t}` } : {};
}
