import { useEffect, useRef } from 'react';

/**
 * useIdleTimeout — calls `onIdle` after `timeoutMs` of no user activity (mouse/touch/key).
 * Pass enabled=false to disable.
 */
export default function useIdleTimeout(onIdle, timeoutMs = 180000, enabled = true) {
  const timerRef = useRef(null);
  useEffect(() => {
    if (!enabled) return undefined;
    const reset = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => onIdle(), timeoutMs);
    };
    const events = ['mousemove', 'mousedown', 'keypress', 'touchstart', 'click', 'wheel'];
    events.forEach(e => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      events.forEach(e => window.removeEventListener(e, reset));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, timeoutMs]);
}

/**
 * Request fullscreen + wake-lock for true kiosk-mode tablets.
 * Returns a cleanup fn that releases the wake lock (call on unmount or unlock).
 */
export async function enterKioskFullscreen() {
  let wakeLock = null;
  try {
    if (document.documentElement.requestFullscreen) {
      await document.documentElement.requestFullscreen({ navigationUI: 'hide' });
    }
  } catch (e) { /* user may have rejected fullscreen — that's OK */ }
  try {
    if ('wakeLock' in navigator) {
      wakeLock = await navigator.wakeLock.request('screen');
    }
  } catch (e) { /* not all browsers support this */ }
  // Block context menu (right-click / long-press) inside kiosk
  const ctxBlocker = (e) => e.preventDefault();
  document.addEventListener('contextmenu', ctxBlocker);
  return () => {
    document.removeEventListener('contextmenu', ctxBlocker);
    if (wakeLock) {
      try { wakeLock.release(); } catch (e) {}
    }
    if (document.fullscreenElement) {
      try { document.exitFullscreen(); } catch (e) {}
    }
  };
}
