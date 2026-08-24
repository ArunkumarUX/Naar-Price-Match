"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { JobStatus, SweepPreview } from "@/lib/types";

type Phase = "idle" | "preview" | "running" | "done" | "error";

export default function SweepPanel({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [preview, setPreview] = useState<SweepPreview | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [msg, setMsg] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.autoconfirmStatus().then((st) => { if (st.status === "running") { setPhase("running"); poll(); } });
    return () => { if (timer.current) clearTimeout(timer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function poll() {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const st = await api.autoconfirmStatus();
      setJob(st);
      if (st.status === "running") { setPhase("running"); poll(); }
      else { setPhase(st.status === "error" ? "error" : "done"); setMsg(st.error || ""); onDone(); }
    }, 1500);
  }

  async function openPreview() {
    setPhase("preview");
    setPreview(await api.autoconfirmPreview());
  }
  async function run() {
    try {
      await api.autoconfirm();
      setPhase("running"); poll();
    } catch (e) { setPhase("error"); setMsg((e as Error).message); }
  }

  return (
    <div className="mb-4 rounded-brand border p-3" style={{ borderColor: "var(--line)", background: "var(--panel)" }}>
      {phase === "idle" && (
        <button className="rounded-pill px-3.5 py-1.5 text-sm font-semibold"
          style={{ background: "var(--panel-2)", color: "var(--ink)", border: "1px solid var(--line)" }}
          onClick={openPreview}>
          ⚡ Auto-confirm high-confidence (sim &gt; 0.9)
        </button>
      )}
      {phase === "preview" && preview && (
        <div className="text-sm">
          Sweep will run store discovery on <b>{preview.pairs}</b> pending pair(s) across{" "}
          <b>{preview.sellers}</b> sellers (~<b>{preview.api_calls_est}</b> ScraperAPI calls, paid), and confirm
          only exact/near-exact name matches (sim &gt; 0.9), tagged <i>auto</i>.
          <div className="mt-2 flex gap-2">
            <button className="rounded-pill px-3.5 py-1.5 text-sm font-bold" style={{ background: "#00B3C2", color: "#02201f" }} onClick={run}>Run sweep</button>
            <button className="rounded-pill border px-3.5 py-1.5 text-sm" style={{ borderColor: "var(--line)" }} onClick={() => setPhase("idle")}>Cancel</button>
          </div>
        </div>
      )}
      {phase === "running" && (
        <div className="text-sm">auto-confirm sweep running… <b className="tnum">{job?.done ?? 0}</b> / <b className="tnum">{job?.total ?? "?"}</b> pair(s)</div>
      )}
      {phase === "done" && (
        <button className="rounded-pill px-3.5 py-1.5 text-sm font-semibold"
          style={{ background: "var(--panel-2)", color: "var(--ink)", border: "1px solid var(--line)" }}
          onClick={openPreview}>
          ⚡ Auto-confirm high-confidence <span style={{ color: "var(--ink-3)" }}>· last sweep confirmed {job?.confirmed ?? 0}</span>
        </button>
      )}
      {phase === "error" && (
        <div className="text-sm" style={{ color: "var(--err)" }}>
          {msg}{" "}
          <button className="ml-2 underline" onClick={() => setPhase("idle")}>dismiss</button>
        </div>
      )}
    </div>
  );
}
