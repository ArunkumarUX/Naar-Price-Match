/** Naar brand tokens — source: DESIGN.md / NAAR Design System */

export const brand = {
  forest: "#021111",
  sandstone: "#F2EFEB",
  turquoise: "#00CCDD",
  turquoiseDim: "#00B3C2",
  cloud: "#FAFAFD",
  slate: "#394141",
  warm: "#85888E",
  pebble: "#D5D8DB",
  mist: "#EAEBED",
  pumpkin: "#FF8931",
  honey: "#FFB21D",
  green: "#078B12",
  violet: "#8B1FD1",
  redOrange: "#FF4318",
  radius: "16px",
  radiusPill: "999px",
} as const;

export const severityColors = {
  critical: brand.redOrange,
  high: brand.pumpkin,
  medium: brand.honey,
  low: brand.green,
} as const;

export const parityStatus = {
  ok: { bg: "bg-naar-green/12", text: "text-naar-green", label: "Parity OK" },
  lower: { bg: "bg-naar-red/12", text: "text-naar-red", label: "Lower" },
  higher: { bg: "bg-naar-pumpkin/12", text: "text-naar-pumpkin", label: "Higher" },
  violation: { bg: "bg-naar-violet/12", text: "text-naar-violet", label: "Violation" },
  missing: { bg: "bg-naar-mist", text: "text-naar-warm", label: "Unmatched" },
} as const;

export const categoryColors: Record<string, string> = {
  Fashion: "bg-turquoise/15 text-forest",
  Consumables: "bg-naar-honey/20 text-forest",
  Beauty: "bg-naar-violet/12 text-forest",
  Health: "bg-naar-green/12 text-forest",
  "Home Essentials": "bg-sandstone text-forest",
  Kids: "bg-turquoise/10 text-forest",
  "Toys & Baby": "bg-naar-pumpkin/15 text-forest",
  "Fashion Accessories": "bg-turquoise/15 text-forest",
};
