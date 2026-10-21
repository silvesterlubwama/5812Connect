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
  accent_color: '',
  login_headline: '',
  login_subtitle: '',
  login_background: '',
  terms: {},
  nav_overrides: {},
  section_overrides: {},
};

// Vocabulary each organisation can reword. Keys are the words this app ships
// with; the value an organisation sets replaces them everywhere they appear in
// page copy — headings, buttons, empty states, toasts.
export const TERM_VOCABULARY = [
  'Member', 'People', 'Campus', 'Marketplace', 'Donation', 'Staff', 'Event',
  'Household', 'Guest', 'Volunteer', 'Department', 'Branch', 'Programme',
];

// Build one case-and-plural aware replacer for the whole vocabulary.
function buildTermReplacer(terms) {
  const pairs = Object.entries(terms || {})
    .map(([from, to]) => [String(from).trim(), String(to || '').trim()])
    .filter(([from, to]) => from && to && from.toLowerCase() !== to.toLowerCase());
  if (!pairs.length) return null;
  // Longest first so "Campus Report" wins over "Campus".
  pairs.sort((a, b) => b[0].length - a[0].length);
  const escape = (w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const plural = (w) => (/(s|x|z|ch|sh)$/i.test(w) ? `${w}es` : /[^aeiou]y$/i.test(w) ? `${w.slice(0, -1)}ies` : `${w}s`);
  const map = new Map();
  const alts = [];
  pairs.forEach(([from, to]) => {
    map.set(from.toLowerCase(), to);
    map.set(plural(from).toLowerCase(), plural(to));
    alts.push(escape(plural(from)), escape(from));
  });
  const re = new RegExp(`\\b(${alts.join('|')})\\b`, 'gi');
  const matchCase = (sample, word) => {
    if (sample === sample.toUpperCase() && sample.length > 1) return word.toUpperCase();
    if (sample[0] === sample[0].toUpperCase()) return word[0].toUpperCase() + word.slice(1);
    return word.toLowerCase();
  };
  // A word only counts when it stands alone. Inside an email address, a link,
  // a file path or an identifier it is data, not wording, and rewriting it
  // would corrupt what the user is actually looking at.
  const GLUE_BEFORE = /[@/\\._\-:?=&#]/;
  const GLUE_AFTER = /[@/\\_\-:?=&#]/;
  return (text) => text.replace(re, (m, _g, offset, full) => {
    const before = offset > 0 ? full[offset - 1] : '';
    const afterIdx = offset + m.length;
    const after = afterIdx < full.length ? full[afterIdx] : '';
    if (before && GLUE_BEFORE.test(before)) return m;
    if (after && GLUE_AFTER.test(after)) return m;
    // "member.probe@…" — a dot followed by more word characters is a domain or
    // an object path, not the end of a sentence.
    if (after === '.' && /[A-Za-z0-9]/.test(full[afterIdx + 1] || '')) return m;
    const hit = map.get(m.toLowerCase());
    return hit ? matchCase(m, hit) : m;
  });
}

const BrandingContext = createContext({ branding: DEFAULTS, refresh: () => {}, term: (w) => w });

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

  // AuthContext fires this on sign-in, organisation switch and sign-out.
  useEffect(() => {
    const onChange = () => refresh();
    window.addEventListener('branding-refresh', onChange);
    return () => window.removeEventListener('branding-refresh', onChange);
  }, [refresh]);

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
    const accentHsl = hexToHslTriplet(branding.accent_color);
    if (branding.accent_color && accentHsl) {
      root.style.setProperty('--accent', accentHsl);
      root.style.setProperty('--brand-accent', branding.accent_color);
    } else {
      root.style.removeProperty('--accent');
      root.style.removeProperty('--brand-accent');
    }
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
  }, [branding.primary_color, branding.accent_color]);

  // Update <title> so the browser tab shows the customised app name.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    if (branding.app_name) document.title = branding.app_name;
  }, [branding.app_name]);

  const replacer = React.useMemo(() => buildTermReplacer(branding.terms), [branding.terms]);

  // Reword the app's own wording for this organisation. Components keep their
  // shipped English; the organisation's vocabulary is applied to rendered text
  // nodes, which is the only way to cover thousands of existing strings without
  // rewriting every page. Costs nothing when no organisation has set a word.
  useEffect(() => {
    if (typeof document === 'undefined' || !replacer) return;
    const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT', 'CODE', 'PRE', 'KBD', 'SAMP']);
    // Never touch a node inside code, an editor, or anything explicitly opted out.
    const skipNode = (node) => {
      let el = node.parentElement;
      while (el && el !== document.body) {
        if (SKIP_TAGS.has(el.tagName) || el.isContentEditable || el.hasAttribute('data-no-term')) return true;
        el = el.parentElement;
      }
      return false;
    };
    let applying = false;
    const rewriteText = (node) => {
      const next = replacer(node.nodeValue || '');
      if (next !== node.nodeValue) {
        applying = true;
        node.nodeValue = next;
        applying = false;
      }
    };
    const rewrite = (root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => (node.nodeValue && node.nodeValue.trim() && !skipNode(node)
          ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
      });
      const hits = [];
      while (walker.nextNode()) hits.push(walker.currentNode);
      hits.forEach(rewriteText);
    };
    rewrite(document.body);
    const observer = new MutationObserver((records) => {
      if (applying) return;
      records.forEach((rec) => {
        if (rec.type === 'characterData') {
          if (!skipNode(rec.target)) rewriteText(rec.target);
          return;
        }
        rec.addedNodes.forEach((n) => {
          if (n.nodeType === 3) {
            if (!skipNode(n)) rewriteText(n);
          } else if (n.nodeType === 1) {
            rewrite(n);
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [replacer]);

  // Single word lookup for components that want to build a string themselves.
  const term = useCallback((word) => (replacer ? replacer(word) : word), [replacer]);

  return (
    <BrandingContext.Provider value={{ branding, refresh, term }}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  return useContext(BrandingContext);
}

// Exported for unit testing the colour conversion path.
export const _hexToHslTriplet = hexToHslTriplet;
