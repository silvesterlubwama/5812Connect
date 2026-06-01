/**
 * BrandingContext — loads the public system_settings/branding doc on mount,
 * exposes app_name / logo_url / primary_color / nav_overrides / section_overrides.
 *
 * Pages call `useBranding()` to read; the admin's BrandingEditor writes via
 * /api/admin/system-settings and then calls `refresh()` so changes are visible
 * immediately without a page reload.
 */
import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import api from '../services/api';

const DEFAULTS = {
  app_name: '58:12 Connect',
  tagline: '',
  logo_url: '',
  primary_color: '',
  nav_overrides: {},
  section_overrides: {},
};

const BrandingContext = createContext({ branding: DEFAULTS, refresh: () => {} });

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DEFAULTS);

  const refresh = useCallback(async () => {
    try {
      const r = await api.get('/admin/system-settings/public');
      setBranding({ ...DEFAULTS, ...(r.data?.branding || {}) });
    } catch { /* keep defaults if unreachable (offline boot, etc) */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Apply the primary-color override globally via a CSS variable so any element
  // that reads `var(--brand-primary)` picks it up automatically.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    if (branding.primary_color) {
      document.documentElement.style.setProperty('--brand-primary', branding.primary_color);
    } else {
      document.documentElement.style.removeProperty('--brand-primary');
    }
  }, [branding.primary_color]);

  // Update <title> so the browser tab shows the customised app name.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    if (branding.app_name) document.title = branding.app_name;
  }, [branding.app_name]);

  return (
    <BrandingContext.Provider value={{ branding, refresh }}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  return useContext(BrandingContext);
}
