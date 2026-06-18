"use client";

import { useHealth } from "@/lib/api";

export function ProductionModeBanner() {
  const { data: health } = useHealth();
  if (!health) return null;

  if (health.production_mode) {
    return (
      <div className="naar-card px-4 py-2.5 text-sm flex flex-wrap items-center gap-3 border-naar-green/30 bg-naar-green/8">
        <span className="font-bold text-forest">● Live production</span>
        <span className="text-naar-slate">
          Claude {health.claude_model} · scraping{" "}
          <a href="https://naar.io/shop" className="text-turquoise-dim font-semibold hover:underline" target="_blank" rel="noreferrer">
            naar.io/shop
          </a>
        </span>
      </div>
    );
  }

  return (
    <div className="naar-card px-4 py-4 text-sm border-naar-honey/30 bg-naar-honey/10 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-bold text-forest">● Demo mode</span>
        <span className="text-naar-slate">Sample prices — not live from Naar Shop or competitors.</span>
      </div>
      <div className="text-naar-slate space-y-2">
        <p className="font-semibold text-forest">Enable live data (3 steps):</p>
        <ol className="list-decimal list-inside space-y-1 text-xs sm:text-sm">
          <li>
            Get an API key from{" "}
            <a href="https://console.anthropic.com/settings/keys" className="text-turquoise-dim font-bold hover:underline" target="_blank" rel="noreferrer">
              console.anthropic.com
            </a>
          </li>
          <li>
            Run in Terminal:
            <code className="block mt-1 p-2 rounded-naar bg-forest/5 text-[11px] overflow-x-auto">
              chmod +x &quot;scripts/enable-production.sh&quot; && &quot;scripts/enable-production.sh&quot;
            </code>
          </li>
          <li>Refresh this page — banner should show <strong>Live production</strong>, then click <strong>Run Scan Now</strong></li>
        </ol>
        <p className="text-[11px] text-naar-warm">
          Or manually create <code>backend/.env</code> with <code>ANTHROPIC_API_KEY</code> and <code>PRODUCTION_MODE=true</code>, then restart the API.
        </p>
      </div>
    </div>
  );
}
