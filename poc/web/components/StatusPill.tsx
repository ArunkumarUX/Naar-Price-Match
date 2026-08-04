const MAP: Record<string, { label: string; fg: string; bg: string }> = {
  MATCHED: { label: "Matched", fg: "var(--good)", bg: "var(--good-bg)" },
  AMBIGUOUS_MATCH: { label: "Needs review", fg: "var(--review)", bg: "var(--review-bg)" },
  SOLD_BY_OTHER: { label: "Other seller", fg: "var(--high)", bg: "var(--high-bg)" },
  PRODUCT_NOT_FOUND: { label: "Not found", fg: "var(--ink-3)", bg: "var(--neutral-bg)" },
  OUT_OF_STOCK: { label: "Out of stock", fg: "var(--review)", bg: "var(--review-bg)" },
  SOURCE_ERROR: { label: "Source error", fg: "var(--err)", bg: "var(--err-bg)" },
  confirmed: { label: "Confirmed", fg: "var(--good)", bg: "var(--good-bg)" },
  rejected: { label: "Not on", fg: "var(--err)", bg: "var(--err-bg)" },
  pending: { label: "Pending", fg: "var(--ink-3)", bg: "var(--neutral-bg)" },
};

export default function StatusPill({ status }: { status: string }) {
  const s = MAP[status] || { label: status, fg: "var(--ink-3)", bg: "var(--neutral-bg)" };
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-xs font-semibold whitespace-nowrap"
      style={{ color: s.fg, background: s.bg }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: "currentColor" }} />
      {s.label}
    </span>
  );
}
