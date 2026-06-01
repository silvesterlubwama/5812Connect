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

// Convert "#rrggbb" or "rgb(r,g,b)" to "H S% L%" string suitable for Tailwind's
// `hsl(var(--primary))` pattern. Returns null if the input is unparseable so the
// caller can leave the theme defaults alone.
function hexToHslTriplet(input) {
  if (!input || typeof input !== 'string') return null;
  let r, g, b;
  const hex = input.trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(hex)) {
    r = parseInt(hex[0] + hex[0], 16);
    g = parseInt(hex[1] + hex[1], 16);
    b = parseInt(hex[2] + hex[2], 16);
  } else if (/^[0-9a-f]{6}$/i.test(hex)) {
    r = parseInt(hex.slice(0, 2), 16);
    g = parseInt(hex.slice(2, 4), 16);
    b = parseInt(hex.slice(4, 6), 16);
  } else {
    const m = input.match(/rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (!m) return null;
    r = +m[1]; g = +m[2]; b = +m[3];
  }
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0; const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
      default:
    }
    h /= 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DEFAULTS);

  const refresh = useCallback(async () => {
    try {
      const r = await api.get('/admin/system-settings/public');
      setBranding({ ...DEFAULTS, ...(r.data?.branding || {}) });
    } catch { /* keep defaults if unreachable (offline boot, etc) */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Apply the primary-color override globally. We override the actual Tailwind
  // CSS variables (`--primary`, `--ring`, `--brand-teal`) so every Tailwind
  // primary-coloured element (buttons, badges, links, focus rings) picks up the
  // brand colour without any per-component change. We also keep `--brand-primary`
  // as a literal-hex variable for places that need the raw value (logos, gradients).
  // `--primary-foreground` is auto-flipped between black/white based on the brand's
  // perceived luminance so text on the primary button stays readable for any hue.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    const hsl = hexToHslTriplet(branding.primary_color);
    if (branding.primary_color && hsl) {
      root.style.setProperty('--brand-primary', branding.primary_color);
      root.style.setProperty('--primary', hsl);
      root.style.setProperty('--ring', hsl);
      root.style.setProperty('--brand-teal', hsl);
      // Pick black-on-bright vs white-on-dark for the foreground based on HSL lightness.
      const m = hsl.match(/\s(\d+)%\s*$/);
      const lightness = m ? parseInt(m[1], 10) : 50;
      root.style.setProperty('--primary-foreground', lightness > 60 ? '240 24% 14%' : '0 0% 100%');
    } else {
      root.style.removeProperty('--brand-primary');
      root.style.removeProperty('--primary');
      root.style.removeProperty('--ring');
      root.style.removeProperty('--brand-teal');
      root.style.removeProperty('--primary-foreground');
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

// Exported for unit testing the colour conversion path.
export const _hexToHslTriplet = hexToHslTriplet;
