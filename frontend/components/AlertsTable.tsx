"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { SeverityBadge } from "@/components/SeverityBadge";
import { useResolveAlert, type Alert } from "@/lib/api";
import { brand } from "@/lib/brand";

const col = createColumnHelper<Alert>();

function ResolveButton({ id }: { id: number }) {
  const resolve = useResolveAlert();
  return (
    <button
      className="text-turquoise-dim hover:underline text-xs font-bold disabled:opacity-50"
      disabled={resolve.isPending}
      onClick={() => resolve.mutate(id)}
    >
      Resolve
    </button>
  );
}

const columns = [
  col.accessor("product_id", { header: "SKU" }),
  col.accessor("platform", { header: "Platform", cell: (i) => i.getValue() || "—" }),
  col.accessor("alert_type", { header: "Type" }),
  col.accessor("naar_price", { header: "Naar ₹", cell: (i) => `₹${i.getValue()?.toFixed(0)}` }),
  col.accessor("competitor_price", {
    header: "Competitor ₹",
    cell: (i) => (i.getValue() ? `₹${i.getValue()?.toFixed(0)}` : "—"),
  }),
  col.accessor("deviation_pct", {
    header: "Deviation",
    cell: (i) => {
      const v = i.getValue();
      if (v == null) return "—";
      return (
        <span className="font-bold" style={{ color: v > 0 ? brand.redOrange : brand.green }}>
          {v > 0 ? "+" : ""}
          {v.toFixed(1)}%
        </span>
      );
    },
  }),
  col.accessor("severity", {
    header: "Severity",
    cell: (i) => <SeverityBadge severity={i.getValue()} />,
  }),
  col.display({
    id: "actions",
    header: "Actions",
    cell: ({ row }) => <ResolveButton id={row.original.id} />,
  }),
];

export function AlertsTable({ alerts, loading }: { alerts: Alert[]; loading?: boolean }) {
  const table = useReactTable({
    data: alerts,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (loading) return <div className="p-8 text-center text-naar-warm">Loading alerts…</div>;

  return (
    <table className="w-full text-sm">
      <thead className="bg-sandstone/70 text-naar-slate text-left">
        {table.getHeaderGroups().map((hg) => (
          <tr key={hg.id}>
            {hg.headers.map((h) => (
              <th
                key={h.id}
                className="px-4 py-3 font-bold text-xs uppercase tracking-wide cursor-pointer select-none"
                onClick={h.column.getToggleSortingHandler()}
              >
                {flexRender(h.column.columnDef.header, h.getContext())}
                {h.column.getIsSorted() === "asc" ? " ↑" : h.column.getIsSorted() === "desc" ? " ↓" : ""}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} className="border-t border-naar-mist hover:bg-sandstone/40 transition-colors">
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id} className="px-4 py-3 text-forest">
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
        {!alerts.length && (
          <tr>
            <td colSpan={8} className="px-4 py-12 text-center text-naar-warm">
              No alerts — run a scan to populate data
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
