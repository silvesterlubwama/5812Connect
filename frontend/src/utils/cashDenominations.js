// Country-specific cash denominations + change calculator
// Used by POS to compute denomination breakdown when cashier gives change.

export const DENOMINATIONS = {
  UGX: [50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50],
  USD: [100, 50, 20, 10, 5, 1, 0.25, 0.10, 0.05, 0.01],
  KES: [1000, 500, 200, 100, 50, 40, 20, 10, 5, 1],
  HTG: [1000, 500, 250, 100, 50, 25, 10, 5, 1],
  THB: [1000, 500, 100, 50, 20, 10, 5, 2, 1],
};

export const DENOM_LABEL = (currency, value) => {
  if (currency === 'USD' && value < 1) {
    return `${(value * 100).toFixed(0)}¢`;
  }
  return `${currency} ${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
};

/**
 * Greedy change breakdown: returns an array of {value, count} from largest to smallest.
 * Handles floating-point edge cases by working in cents (×100).
 */
export function breakChange(amount, currency = 'UGX') {
  const denoms = DENOMINATIONS[currency] || DENOMINATIONS.UGX;
  const result = [];
  // Work in integer cents to avoid float drift
  let remaining = Math.round(Number(amount) * 100);
  for (const d of denoms) {
    const dCents = Math.round(d * 100);
    const count = Math.floor(remaining / dCents);
    if (count > 0) {
      result.push({ value: d, count });
      remaining -= count * dCents;
    }
  }
  return { breakdown: result, leftover: remaining / 100 };
}

/** Sum a denomination breakdown back to a total (for verification). */
export function sumBreakdown(breakdown) {
  return breakdown.reduce((s, b) => s + b.value * b.count, 0);
}

/** Country code → currency map (best-effort default). */
export const COUNTRY_TO_CURRENCY = {
  Uganda: 'UGX', UG: 'UGX',
  Kenya: 'KES', KE: 'KES',
  USA: 'USD', 'United States': 'USD', US: 'USD',
  Haiti: 'HTG', HT: 'HTG',
  Thailand: 'THB', TH: 'THB',
};
