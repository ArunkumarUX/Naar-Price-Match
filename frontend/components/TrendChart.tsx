"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Severity } from "@/lib/api";
import { brand, severityColors } from "@/lib/brand";

const SEVERITY_LABELS: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

type ChartPoint = { sev: string; count: number };

function ChartTooltip({
  active,
  payload,
  dark,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartPoint }>;
  dark?: boolean;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  const label = SEVERITY_LABELS[point.sev] || point.sev;

  return (
    <div
      className={`rounded-xl px-3 py-2 shadow-naar text-xs border ${
        dark ? "bg-forest border-white/15 text-cloud" : "bg-cloud border-naar-mist text-forest"
      }`}
      role="status"
    >
      <p className="font-bold">{label}</p>
      <p className={dark ? "text-cloud/65 mt-0.5" : "text-naar-slate mt-0.5"}>
        {point.count} open alert{point.count === 1 ? "" : "s"}
      </p>
    </div>
  );
}

export function TrendChart({ data, dark }: { data: ChartPoint[]; dark?: boolean }) {
  const tickColor = dark ? "rgba(250,250,253,0.55)" : brand.slate;
  const gridColor = dark ? "rgba(255,255,255,0.07)" : "rgba(2,17,17,0.06)";
  const total = data.reduce((sum, d) => sum + d.count, 0);
  const maxCount = Math.max(...data.map((d) => d.count), 0);
  const yMax = Math.max(maxCount + 1, 4);

  const summaryText = data
    .map((d) => `${SEVERITY_LABELS[d.sev] || d.sev}: ${d.count}`)
    .join(", ");

  if (total === 0) {
    return (
      <div
        className="h-[220px] flex flex-col items-center justify-center text-center px-6"
        role="img"
        aria-label="Alert volume chart. No open alerts across critical, high, medium, and low severity."
      >
        <div
          className={`w-12 h-12 rounded-full flex items-center justify-center mb-3 ${
            dark ? "bg-white/8 text-turquoise" : "bg-turquoise/10 text-turquoise-dim"
          }`}
          aria-hidden
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 19V5" strokeLinecap="round" />
            <path d="M4 19h16" strokeLinecap="round" />
            <path d="M8 15v-4" strokeLinecap="round" />
            <path d="M12 15V8" strokeLinecap="round" />
            <path d="M16 15v-2" strokeLinecap="round" />
          </svg>
        </div>
        <p className={`text-sm font-bold ${dark ? "text-cloud" : "text-forest"}`}>No open alerts</p>
        <p className={`text-xs mt-1 max-w-[240px] leading-relaxed ${dark ? "text-cloud/50" : "text-naar-warm"}`}>
          When mismatches appear, severity volume will show here as Critical → Low.
        </p>
      </div>
    );
  }

  return (
    <div
      role="img"
      aria-label={`Alert volume chart. ${summaryText}. Total ${total} open alerts.`}
    >
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke={gridColor} strokeDasharray="4 6" />
          <XAxis
            dataKey="sev"
            tickFormatter={(v) => SEVERITY_LABELS[v] || v}
            tick={{ fontSize: 11, fill: tickColor, fontWeight: 600 }}
            axisLine={false}
            tickLine={false}
            dy={6}
          />
          <YAxis
            allowDecimals={false}
            domain={[0, yMax]}
            tick={{ fontSize: 11, fill: tickColor }}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <Tooltip
            cursor={{ fill: dark ? "rgba(255,255,255,0.04)" : "rgba(2,17,17,0.03)", radius: 8 }}
            content={<ChartTooltip dark={dark} />}
          />
          <Bar dataKey="count" radius={[10, 10, 4, 4]} maxBarSize={48}>
            {data.map((d) => (
              <Cell key={d.sev} fill={severityColors[d.sev as Severity] || brand.turquoise} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Color is not the only signal — legend duplicates labels + counts */}
      <ul className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2" aria-label="Severity breakdown">
        {data.map((d) => (
          <li
            key={d.sev}
            className={`flex items-center gap-2 rounded-pill px-2.5 py-1.5 text-[11px] font-semibold ${
              dark ? "bg-white/6 text-cloud/80" : "bg-sandstone/70 text-naar-slate"
            }`}
          >
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ background: severityColors[d.sev as Severity] || brand.turquoise }}
              aria-hidden
            />
            <span className="capitalize">{SEVERITY_LABELS[d.sev] || d.sev}</span>
            <span className={`ml-auto tabular-nums font-extrabold ${dark ? "text-cloud" : "text-forest"}`}>
              {d.count}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
