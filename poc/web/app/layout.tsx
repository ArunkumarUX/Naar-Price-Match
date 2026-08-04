import "./globals.css";
import type { Metadata } from "next";
import Providers from "./providers";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "Naar price-match",
  description: "Annotate marketplace stores and view store-first price-match results.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
