import type { Config } from "tailwindcss";

// Naar brand tokens (source: DESIGN.md / frontend/lib/brand.ts)
const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        forest: "#021111",
        sandstone: "#F2EFEB",
        cloud: "#FAFAFD",
        turquoise: { DEFAULT: "#00CCDD", dim: "#00B3C2" },
        slate: "#394141",
        warm: "#85888E",
        pebble: "#D5D8DB",
        mist: "#EAEBED",
        pumpkin: "#FF8931",
        honey: "#FFB21D",
        green: "#078B12",
        violet: "#8B1FD1",
        redorange: "#FF4318",
      },
      borderRadius: { brand: "16px", pill: "999px" },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
