"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

function ThemeToggle() {
  return (
    <button
      type="button"
      className="rounded-pill border px-3 py-1.5 text-[13px]"
      style={{ borderColor: "var(--line)", background: "var(--panel)", color: "var(--ink-2)" }}
      onClick={() => {
        const r = document.documentElement;
        const cur = r.getAttribute("data-theme") ||
          (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
        r.setAttribute("data-theme", cur === "dark" ? "light" : "dark");
      }}
    >
      ◐ Theme
    </button>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const tab = (href: string, label: string) => {
    const active = path === href;
    return (
      <Link
        href={href}
        className="rounded-pill px-3.5 py-1.5 text-sm font-semibold"
        style={{
          background: active ? "var(--ink)" : "var(--panel)",
          color: active ? "var(--bg)" : "var(--ink-2)",
          border: `1px solid ${active ? "var(--ink)" : "var(--line)"}`,
        }}
      >
        {label}
      </Link>
    );
  };
  return (
    <div className="mx-auto max-w-6xl px-5 pb-16 pt-7">
      <header className="flex flex-wrap items-center gap-3.5">
        <div
          className="grid h-9 w-9 flex-none place-items-center rounded-[11px] font-extrabold"
          style={{ background: "linear-gradient(135deg,#00CCDD,#00B3C2)", color: "#02201f" }}
        >
          n
        </div>
        <div>
          <h1 className="m-0 text-[19px] font-extrabold">Naar price-match</h1>
          <div className="text-[13px]" style={{ color: "var(--ink-3)" }}>
            Store-first parity across confirmed marketplace stores
          </div>
        </div>
        <nav className="ml-2 flex gap-2">
          {tab("/", "Annotate")}
          {tab("/results", "Results")}
        </nav>
        <div className="flex-1" />
        <ThemeToggle />
      </header>
      <main className="mt-6">{children}</main>
    </div>
  );
}
