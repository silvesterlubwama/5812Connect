/**
 * Centralised role-based access helpers. Mirrors `backend/deps.py` PRIVILEGED_ROLES.
 * Use these so we don't sprinkle hard-coded role arrays across the codebase.
 */

const DIRECTOR_PLUS = new Set([
  'admin',
  'system_admin',
  'Executive Director',
  'Adviser',
  'Director',
]);

const MANAGER_PLUS = new Set([
  ...Array.from(DIRECTOR_PLUS),
  'Manager',
]);

const STAFF_PLUS = new Set([
  ...Array.from(MANAGER_PLUS),
  'Leader',
  'Coordinator',
  'Staff',
  'HR',
  'Volunteer',
]);

export const hasDirectorAccess = (user) => DIRECTOR_PLUS.has(user?.role || '');
export const hasManagerAccess = (user) => MANAGER_PLUS.has(user?.role || '');
export const hasStaffAccess = (user) => STAFF_PLUS.has(user?.role || '');

/**
 * Hook returning true only when the browser tab is visible. Lets pollers
 * pause work when the tab is hidden — saves backend load on background tabs.
 *   const visible = useDocumentVisible();
 *   useEffect(() => { if (!visible) return; ... }, [visible]);
 */
import { useEffect, useState } from 'react';
export const useDocumentVisible = () => {
  const [visible, setVisible] = useState(
    typeof document === 'undefined' ? true : document.visibilityState === 'visible'
  );
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const handler = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);
  return visible;
};
