"use client";

import { NaarShopCompareTable } from "@/components/NaarShopCompareTable";
import { PageHeader } from "@/components/PageHeader";
import { useSellers } from "@/lib/api";

export default function ComparePage() {
  const { data: sellers } = useSellers();

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-8 pb-12">
      <PageHeader
        eyebrow="naar.io/shop · Price Parity"
        title="Naar Shop vs Competitors"
        description={`Exact price check for every product on Naar Shop against Amazon, Flipkart, Meesho and ${sellers?.count ?? 0} authorized seller websites — same prices you see on naar.io.`}
      />
      <NaarShopCompareTable />
    </main>
  );
}
