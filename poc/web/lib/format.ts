export const rupees = (v: number | null | undefined) =>
  v == null ? "—" : "₹" + v.toLocaleString("en-IN");

/** Δ vs Naar = marketplace(unit) price − Naar price. Positive = Naar cheaper (good). */
export function delta(row: {
  naar_selling_price: number | null;
  marketplace_selling_price: number | null;
  marketplace_unit_price: number | null;
}): number | null {
  const mkt = row.marketplace_unit_price ?? row.marketplace_selling_price;
  if (mkt == null || row.naar_selling_price == null) return null;
  return mkt - row.naar_selling_price;
}
export const deltaText = (d: number | null) => (d == null ? "—" : (d > 0 ? "+" : "") + Math.round(d));
