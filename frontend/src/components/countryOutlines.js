/**
 * Simplified country outline SVG paths for badge watermarks.
 * Each entry: { viewBox, path } - designed to be rendered as faint watermarks.
 */
const COUNTRY_OUTLINES = {
  Uganda: {
    viewBox: '0 0 100 100',
    path: 'M30 8 L50 5 L65 8 L75 15 L80 30 L85 45 L82 60 L78 70 L70 80 L60 88 L50 92 L40 90 L30 82 L22 70 L18 55 L20 40 L22 28 L25 18 Z',
  },
  Kenya: {
    viewBox: '0 0 100 120',
    path: 'M45 5 L60 8 L72 15 L80 25 L85 40 L90 55 L88 70 L82 85 L70 100 L55 110 L40 115 L30 108 L20 95 L15 80 L18 65 L22 50 L28 35 L35 20 Z',
  },
  Haiti: {
    viewBox: '0 0 120 80',
    path: 'M10 35 L25 25 L40 20 L55 22 L70 18 L85 22 L95 30 L105 25 L115 30 L110 40 L100 48 L85 52 L70 55 L55 50 L45 55 L35 58 L25 52 L15 45 Z',
  },
  Thailand: {
    viewBox: '0 0 80 130',
    path: 'M35 5 L50 8 L60 15 L65 28 L62 40 L58 48 L65 55 L70 65 L68 78 L60 88 L50 95 L42 105 L38 115 L35 125 L30 118 L28 105 L25 92 L20 80 L18 68 L22 55 L18 45 L15 35 L20 22 L28 12 Z',
  },
  USA: {
    viewBox: '0 0 160 100',
    path: 'M10 30 L25 25 L40 28 L55 22 L70 20 L85 22 L100 18 L115 20 L130 25 L145 30 L155 35 L150 45 L140 50 L130 48 L120 52 L110 55 L100 50 L90 55 L80 60 L70 58 L60 62 L50 60 L40 65 L30 60 L20 55 L12 45 Z',
  },
  // Fallback for unrecognized countries - a simple globe
  _default: {
    viewBox: '0 0 100 100',
    path: 'M50 5 C75 5 95 25 95 50 C95 75 75 95 50 95 C25 95 5 75 5 50 C5 25 25 5 50 5 Z M50 5 L50 95 M5 50 L95 50 M20 20 Q50 35 80 20 M20 80 Q50 65 80 80',
  },
};

export function getCountryOutline(country) {
  if (!country) return COUNTRY_OUTLINES._default;
  // Try exact match first, then case-insensitive
  if (COUNTRY_OUTLINES[country]) return COUNTRY_OUTLINES[country];
  const key = Object.keys(COUNTRY_OUTLINES).find(
    k => k.toLowerCase() === country.toLowerCase()
  );
  return key ? COUNTRY_OUTLINES[key] : COUNTRY_OUTLINES._default;
}

/**
 * Inline SVG string for a country watermark, used inside badge HTML.
 * Returns an SVG element string positioned absolutely as a faint background.
 */
export function countryWatermarkSvg(country, width = 120, height = 120, color = 'rgba(255,255,255,0.06)') {
  const outline = getCountryOutline(country);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${outline.viewBox}" width="${width}" height="${height}" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);opacity:1;pointer-events:none"><path d="${outline.path}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/></svg>`;
}

/**
 * NFC icon SVG string for embedding in badges (staff only).
 */
export function nfcIconSvg(size = 14, color = '#fbbf24') {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle"><path d="M6 8.32a7.43 7.43 0 0 1 0 7.36"/><path d="M9.46 6.21a11.76 11.76 0 0 1 0 11.58"/><path d="M12.91 4.1a15.91 15.91 0 0 1 .01 15.8"/><path d="M16.37 2a20.16 20.16 0 0 1 0 20"/></svg>`;
}
