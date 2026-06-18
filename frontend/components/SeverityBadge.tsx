import type { Severity } from "@/lib/api";
import { severityColors } from "@/lib/brand";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className="rounded-pill px-2.5 py-0.5 text-[10px] font-bold text-white uppercase tracking-wide"
      style={{ background: severityColors[severity] || "#85888E" }}
    >
      {severity}
    </span>
  );
}
