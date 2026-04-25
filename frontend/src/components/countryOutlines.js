/**
 * Real country outline SVG paths for badge watermarks using world-map-country-shapes.
 * Uses ISO 3166-1 alpha-2 country codes.
 */
import rawCountriesData from 'world-map-country-shapes';

// Handle both ESM default export and CJS module formats
const countriesData = rawCountriesData?.default || rawCountriesData;

// Build lookup by ISO code
const _byCode = {};
if (Array.isArray(countriesData)) {
  countriesData.forEach(c => { if (c && c.id) _byCode[c.id] = c.shape; });
} else if (countriesData && typeof countriesData === 'object') {
  Object.keys(countriesData).forEach(k => {
    const c = countriesData[k];
    if (c && c.id) _byCode[c.id] = c.shape;
    else if (c && typeof c === 'string' && k.length === 2) _byCode[k] = c;
  });
}

// Country name -> ISO code mapping for common 58:12 Global locations
const COUNTRY_TO_CODE = {
  'uganda': 'UG', 'kenya': 'KE', 'haiti': 'HT', 'thailand': 'TH',
  'usa': 'US', 'united states': 'US', 'united states of america': 'US',
  'canada': 'CA', 'uk': 'GB', 'united kingdom': 'GB', 'south africa': 'ZA',
  'tanzania': 'TZ', 'rwanda': 'RW', 'congo': 'CD', 'ethiopia': 'ET',
  'nigeria': 'NG', 'ghana': 'GH', 'india': 'IN', 'brazil': 'BR',
  'mexico': 'MX', 'colombia': 'CO', 'peru': 'PE', 'philippines': 'PH',
  'indonesia': 'ID', 'australia': 'AU', 'germany': 'DE', 'france': 'FR',
  'italy': 'IT', 'spain': 'ES', 'japan': 'JP', 'south korea': 'KR',
  'china': 'CN', 'egypt': 'EG', 'morocco': 'MA', 'senegal': 'SN',
  'mozambique': 'MZ', 'zambia': 'ZM', 'malawi': 'MW', 'cameroon': 'CM',
};

/**
 * Get the SVG path data for a country by name or ISO code.
 * Returns { path, viewBox } or null if not found.
 */
export function getCountryOutline(countryOrCode) {
  if (!countryOrCode) return null;
  const input = countryOrCode.trim();
  // Try as ISO code directly (2 letters)
  if (input.length === 2) {
    const shape = _byCode[input.toUpperCase()];
    if (shape) return { path: shape, viewBox: '0 0 2000 1000' };
  }
  // Try as country_code field
  if (input.length <= 3) {
    const shape = _byCode[input.toUpperCase()];
    if (shape) return { path: shape, viewBox: '0 0 2000 1000' };
  }
  // Try name -> code mapping
  const code = COUNTRY_TO_CODE[input.toLowerCase()];
  if (code) {
    const shape = _byCode[code];
    if (shape) return { path: shape, viewBox: '0 0 2000 1000' };
  }
  return null;
}

/**
 * NFC icon SVG string for embedding in badges (staff only).
 */
export function nfcIconSvg(size = 14, color = '#fbbf24') {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle"><path d="M6 8.32a7.43 7.43 0 0 1 0 7.36"/><path d="M9.46 6.21a11.76 11.76 0 0 1 0 11.58"/><path d="M12.91 4.1a15.91 15.91 0 0 1 .01 15.8"/><path d="M16.37 2a20.16 20.16 0 0 1 0 20"/></svg>`;
}
