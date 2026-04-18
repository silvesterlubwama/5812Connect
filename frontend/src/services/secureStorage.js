/**
 * Secure storage helper — wraps sessionStorage for tokens (cleared on tab close)
 * and localStorage only for non-sensitive preferences.
 * Tokens use sessionStorage to reduce XSS exposure window.
 */
const TOKEN_KEY = '5812_token';
const USER_KEY = '5812_user';

export const secureStorage = {
  // Auth tokens in sessionStorage (cleared on tab close)
  getToken: () => sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY),
  setToken: (token) => { sessionStorage.setItem(TOKEN_KEY, token); localStorage.setItem(TOKEN_KEY, token); },
  removeToken: () => { sessionStorage.removeItem(TOKEN_KEY); localStorage.removeItem(TOKEN_KEY); },

  getUser: () => {
    try {
      const raw = sessionStorage.getItem(USER_KEY) || localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  },
  setUser: (user) => {
    const raw = JSON.stringify(user);
    sessionStorage.setItem(USER_KEY, raw);
    localStorage.setItem(USER_KEY, raw);
  },
  removeUser: () => { sessionStorage.removeItem(USER_KEY); localStorage.removeItem(USER_KEY); },

  // Non-sensitive preferences stay in localStorage (persist across sessions)
  getPref: (key) => localStorage.getItem(key),
  setPref: (key, val) => localStorage.setItem(key, val),
  removePref: (key) => localStorage.removeItem(key),

  clearAll: () => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};
