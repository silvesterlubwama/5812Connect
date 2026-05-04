// Cart calculation utilities — applies bulk tier discounts + packaging cost + units/pack tracking.
// All prices in line items are stored gross-pack (no discount).
// At display/checkout we apply: tier discount (per product across variants) + packaging.

/**
 * Sum quantities of all cart items belonging to the same product.
 * Used for tier-discount eligibility (volume bought of the product across all variants).
 */
export function productQty(cart, productId) {
  return cart
    .filter((i) => i.product_id === productId)
    .reduce((s, i) => s + (Number(i.qty) || 0), 0);
}

/**
 * Pick the highest-tier discount whose min_qty <= total qty.
 * Capped at max_discount_pct if provided.
 */
export function pickTierDiscount(tiers, totalQty, maxPct = 100) {
  if (!Array.isArray(tiers) || tiers.length === 0) return 0;
  let pct = 0;
  for (const t of tiers) {
    const min = Number(t.min_qty) || 0;
    const d = Number(t.discount_pct) || 0;
    if (totalQty >= min && d > pct) pct = d;
  }
  return Math.min(pct, Number(maxPct) || 100);
}

/**
 * Compute line totals for a single cart item.
 * item: { qty, unit_price, units_per_pack, packaging_cost, packaging_label, include_packaging, product_id, variant_id, name, ... }
 * product: full product record (for tiers); pass null if not available.
 * cart: full cart array (used to compute per-product totals across variants).
 *
 * Returns: { subtotal, packaging_total, discount_pct, discount_amount, line_total }
 */
export function calcLine(item, cart = [], product = null) {
  const qty = Number(item.qty) || 0;
  const unit = Number(item.unit_price) || 0;
  const unitsPerPack = Number(item.units_per_pack || 1);
  const subtotal = qty * unit;

  const includePack = item.include_packaging !== false;
  const packCost = Number(item.packaging_cost || 0);
  const packagingTotal = includePack ? qty * packCost : 0;

  const tiers = product?.qty_discount_tiers || [];
  const maxPct = product?.max_discount_pct ?? 100;
  // Tier eligibility uses TOTAL product qty across all variants in cart
  const totalProductQty = product ? productQty(cart, product.id) : qty;
  const discountPct = pickTierDiscount(tiers, totalProductQty, maxPct);
  // Discount applies to the variant subtotal (NOT packaging — the tray itself is at-cost)
  const discountAmount = subtotal * (discountPct / 100);
  const lineTotal = subtotal + packagingTotal - discountAmount;

  return {
    qty,
    units_per_pack: unitsPerPack,
    base_units: qty * unitsPerPack,
    subtotal,
    packaging_total: packagingTotal,
    discount_pct: discountPct,
    discount_amount: discountAmount,
    line_total: lineTotal,
  };
}

/**
 * Compute cart totals.
 * Returns: { subtotal, packaging_total, discount_total, total }
 */
export function calcCart(cart, productsById = {}) {
  let subtotal = 0;
  let packagingTotal = 0;
  let discountTotal = 0;
  for (const item of cart) {
    const product = productsById[item.product_id] || null;
    const r = calcLine(item, cart, product);
    subtotal += r.subtotal;
    packagingTotal += r.packaging_total;
    discountTotal += r.discount_amount;
  }
  return {
    subtotal,
    packaging_total: packagingTotal,
    discount_total: discountTotal,
    total: subtotal + packagingTotal - discountTotal,
  };
}
