/**
 * OfflineBanner — sits at the top of the app shell, shows when the browser is
 * offline (navigator.onLine === false). Service Worker (`/sw.js`) already
 * serves cached pages + API responses, so the app keeps working, but the user
 * deserves to know writes won't reach the server until connectivity returns.
 */
import React, { useEffect, useState } from 'react';
import { WifiOff, Wifi } from 'lucide-react';

export default function OfflineBanner() {
  const [online, setOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const [recovered, setRecovered] = useState(false);

  useEffect(() => {
    const onUp = () => { setOnline(true); setRecovered(true); setTimeout(() => setRecovered(false), 4000); };
    const onDown = () => { setOnline(false); setRecovered(false); };
    window.addEventListener('online', onUp);
    window.addEventListener('offline', onDown);
    return () => { window.removeEventListener('online', onUp); window.removeEventListener('offline', onDown); };
  }, []);

  if (online && !recovered) return null;
  if (online && recovered) {
    return (
      <div className="fixed top-0 left-0 right-0 z-50 bg-emerald-600 text-white text-xs text-center py-1.5 flex items-center justify-center gap-2" data-testid="online-banner">
        <Wifi size={12} /> Back online — syncing…
      </div>
    );
  }
  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500 text-amber-950 text-xs text-center py-1.5 flex items-center justify-center gap-2 font-medium" data-testid="offline-banner">
      <WifiOff size={12} /> Offline — read-only mode. Recent changes will sync when connectivity returns.
    </div>
  );
}
