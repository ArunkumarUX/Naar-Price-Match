"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Severity } from "@/lib/api";
import { brand, severityColors } from "@/lib/brand";

export function TrendChart({ data, dark }: { data: { sev: string; count: number }[]; dark?: boolean }) {
  const tickColor = dark ? "rgba(250,250,253,0.5)" : brand.slate;
  const gridColor = dark ? "rgba(255,255,255,0.06)" : "rgba(2,17,17,0.04)";

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data}>
        <XAxis dataKey="sev" tick={{ fontSize: 11, fill: tickColor, fontWeight: 600 }} axisLine={false} tickLine={false} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: tickColor }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{
            background: dark ? brand.forest : brand.cloud,
            border: `1px solid ${dark ? "rgba(255,255,255,0.1)" : brand.mist}`,
            borderRadius: 12,
            fontSize: 12,
            color: dark ? brand.cloud : brand.forest,
          }}
        />
        <Bar dataKey="count" radius={[8, 8, 0, 0]}>
          {data.map((d) => (
            <Cell key={d.sev} fill={severityColors[d.sev as Severity] || brand.turquoise} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
