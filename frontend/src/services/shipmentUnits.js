// Mirror of backend/shipment_units.py for client-side display + input
// parsing. Keeps the round-trip stable so when a user types "2'9\"" or
// "5lb 8oz" we send the parsed cm/kg, the backend re-parses it (idempotent
// on already-cm/kg input), and the next render shows the same string.

const CM_PER_INCH = 2.54;
const KG_PER_LB = 0.45359237;
const KG_PER_OZ = 0.028349523125;

const DIM_FEET_INCHES_RE = /^\s*(?:(\d+(?:\.\d+)?)\s*(?:'|ft|feet|foot)\s*)?(?:(\d+(?:\.\d+)?)\s*(?:"|in|inch|inches))?\s*$/i;
const WEIGHT_LB_OZ_RE = /^\s*(?:(\d+(?:\.\d+)?)\s*(?:lb|lbs|pound|pounds)\s*)?(?:(\d+(?:\.\d+)?)\s*(?:oz|ounce|ounces))?\s*$/i;

export function parseDimToCm(value, units = 'metric') {
  if (value === null || value === undefined || value === '') return 0;
  if (typeof value === 'number') return value * (units === 'imperial' ? CM_PER_INCH : 1);
  const s = String(value).trim().toLowerCase();
  if (!s) return 0;
  if (s.endsWith('mm')) return parseFloat(s.slice(0, -2)) / 10 || 0;
  if (s.endsWith('cm')) return parseFloat(s.slice(0, -2)) || 0;
  if (s.endsWith('m') && !s.endsWith('cm') && !s.endsWith('mm')) {
    return (parseFloat(s.slice(0, -1)) || 0) * 100;
  }
  if (/['"]|ft|in|foot|feet|inch/i.test(s)) {
    const m = s.match(DIM_FEET_INCHES_RE);
    if (m) {
      const ft = parseFloat(m[1] || 0);
      const inches = parseFloat(m[2] || 0);
      return (ft * 12 + inches) * CM_PER_INCH;
    }
  }
  const n = parseFloat(s);
  if (Number.isNaN(n)) return 0;
  return n * (units === 'imperial' ? CM_PER_INCH : 1);
}

export function parseWeightToKg(value, units = 'metric') {
  if (value === null || value === undefined || value === '') return 0;
  if (typeof value === 'number') return value * (units === 'imperial' ? KG_PER_LB : 1);
  const s = String(value).trim().toLowerCase();
  if (!s) return 0;
  if (s.endsWith('kg')) return parseFloat(s.slice(0, -2)) || 0;
  if (s.endsWith('g') && !s.endsWith('kg')) return (parseFloat(s.slice(0, -1)) || 0) / 1000;
  if (/lb|oz|pound|ounce/i.test(s)) {
    const m = s.match(WEIGHT_LB_OZ_RE);
    if (m) {
      const lbs = parseFloat(m[1] || 0);
      const ozs = parseFloat(m[2] || 0);
      return lbs * KG_PER_LB + ozs * KG_PER_OZ;
    }
  }
  const n = parseFloat(s);
  if (Number.isNaN(n)) return 0;
  return n * (units === 'imperial' ? KG_PER_LB : 1);
}

export function formatDimCm(cm, units = 'metric') {
  const n = Number(cm) || 0;
  if (units === 'imperial') {
    const totalIn = n / CM_PER_INCH;
    const feet = Math.floor(totalIn / 12);
    const inches = totalIn - feet * 12;
    if (feet && inches >= 0.05) return `${feet}'${Math.round(inches)}"`;
    if (feet) return `${feet}'`;
    return `${inches.toFixed(1)}"`;
  }
  if (n >= 100) return `${(n / 100).toFixed(2)} m`;
  return `${n.toFixed(1)} cm`;
}

export function formatWeightKg(kg, units = 'metric') {
  const n = Number(kg) || 0;
  if (units === 'imperial') {
    const totalLb = n / KG_PER_LB;
    const lbs = Math.floor(totalLb);
    const ozs = (totalLb - lbs) * 16;
    if (lbs && ozs >= 0.5) return `${lbs} lb ${Math.round(ozs)} oz`;
    if (lbs) return `${lbs} lb`;
    return `${ozs.toFixed(1)} oz`;
  }
  if (n < 1) return `${(n * 1000).toFixed(0)} g`;
  return `${n.toFixed(2)} kg`;
}

// Helper for input placeholders — "33 (cm)" or "2'9\" (or 33in)"
export function dimPlaceholder(units = 'metric') {
  return units === 'imperial' ? `e.g. 2'9" or 33in` : 'e.g. 84 (cm)';
}
export function weightPlaceholder(units = 'metric') {
  return units === 'imperial' ? 'e.g. 5lb 8oz' : 'e.g. 2.3 (kg)';
}
