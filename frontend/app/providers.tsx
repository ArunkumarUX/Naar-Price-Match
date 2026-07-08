"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { NaarLogo } from "@/components/NaarLogo";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/compare", label: "Compare" },
  { href: "/sellers", label: "Sellers" },
  { href: "/alerts", label: "Alerts" },
  { href: "/products", label: "Products" },
];

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      className={`relative text-sm font-semibold transition-colors pb-1 ${
        active ? "text-forest" : "text-naar-slate hover:text-forest"
      }`}
    >
      {label}
      {active && (
        <span className="absolute left-0 right-0 -bottom-0.5 h-0.5 rounded-full bg-turquoise" />
      )}
    </Link>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={client}>
      <header className="naar-nav">
        <div className="max-w-screen-xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <NaarLogo subtitle="Shop Parity" size="lg" />
          <nav className="hidden md:flex items-center gap-7">
            {NAV.map((n) => (
              <NavLink key={n.href} {...n} />
            ))}
          </nav>
        </div>
      </header>
      {children}
      <footer className="border-t border-naar-mist bg-forest text-cloud/50 mt-16">
        <div className="max-w-screen-xl mx-auto px-6 py-8 flex flex-col sm:flex-row justify-between items-center gap-4 text-sm">
          <NaarLogo variant="light" size="sm" />
          <span>
            Blaze your own trail ·{" "}
            <a href="https://naar.io" className="text-turquoise font-semibold hover:underline" target="_blank" rel="noreferrer">
              naar.io
            </a>
          </span>
        </div>
      </footer>
    </QueryClientProvider>
  );
}
