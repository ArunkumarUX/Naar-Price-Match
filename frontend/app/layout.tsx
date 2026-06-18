import type { Metadata } from "next";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Price Parity AI — Naar",
  description: "Naar price intelligence — monitor parity across Amazon, Flipkart, Meesho and seller websites.",
  icons: {
    icon: "/brand/naar-app-icon.svg",
    apple: "/brand/naar-app-icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
