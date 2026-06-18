/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        forest: "#021111",
        sandstone: "#F2EFEB",
        turquoise: "#00CCDD",
        "turquoise-dim": "#00B3C2",
        cloud: "#FAFAFD",
        "naar-slate": "#394141",
        "naar-warm": "#85888E",
        "naar-pebble": "#D5D8DB",
        "naar-mist": "#EAEBED",
        "naar-pumpkin": "#FF8931",
        "naar-honey": "#FFB21D",
        "naar-green": "#078B12",
        "naar-violet": "#8B1FD1",
        "naar-red": "#FF4318",
      },
      fontFamily: {
        sans: ["Lufga", "Plus Jakarta Sans", "system-ui", "sans-serif"],
        display: ["Lufga", "Plus Jakarta Sans", "system-ui", "sans-serif"],
      },
      borderRadius: {
        naar: "16px",
        pill: "999px",
      },
      boxShadow: {
        naar: "0 8px 32px rgba(2, 17, 17, 0.08)",
        "naar-lg": "0 24px 64px rgba(2, 17, 17, 0.12)",
        "turquoise-glow": "0 6px 24px rgba(0, 204, 221, 0.35)",
      },
    },
  },
  plugins: [],
};
