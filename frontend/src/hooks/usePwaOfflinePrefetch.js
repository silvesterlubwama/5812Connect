import { useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

/**
 * usePwaOfflinePrefetch — on login (or first mount when already logged in),
 * ask the service worker to preload the "offline essentials" set:
 *   • auth/me, dashboard stats, locations
 *   • today's roster (events + tasks + director-digest-preview)
 *   • the caller's own wallet badge (via /members/{id}/qr-code + /profile-photo)
 *   • checkpoint scanners list (so security desks can operate offline)
 *
 * Runs once per session. The SW handles the actual caching + revalidation.
 */
export default function usePwaOfflinePrefetch() {
  const { user } = useAuth();

  useEffect(() => {
    if (!user) return;
    if (!('serviceWorker' in navigator) || !navigator.serviceWorker.controller) return;

    const today = new Date().toISOString().slice(0, 10);
    const urls = [
      '/api/auth/me',
      '/api/dashboard/stats',
      '/api/locations',
      '/api/tasks',
      `/api/events?from=${today}&to=${today}`,
      '/api/tasks/director-digest-preview',
      '/api/access/checkpoints',
    ];
    if (user.id) {
      urls.push(`/api/members/${user.id}/qr-code`);
      urls.push(`/api/members/${user.id}/profile-photo`);
    }

    // Auth token so the SW can authenticate against the API for these preloads
    let token = null;
    try { token = localStorage.getItem('token'); } catch (e) { /* SSR-safe */ }

    navigator.serviceWorker.controller.postMessage({
      type: 'prefetch-offline-set',
      urls,
      token,
    });
  }, [user?.id]);  // eslint-disable-line react-hooks/exhaustive-deps
}
