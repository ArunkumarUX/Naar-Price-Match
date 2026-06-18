# Naar Website Design System

This file captures the local design rules for `naar-website-v2.html`. It follows the agent-readable design-system style from VoltAgent `awesome-design-md`, but the brand source of truth is `NAAR_Design System.pdf`.

## Brand

- Promise: Blaze your own trail.
- Product idea: Stories become storefronts.
- Personality: Approachable, fresh, grounded, simple, human, dynamic, distinctive, bold.
- Visual mood: Light, tactile, editorial, high-contrast, fast, creator-led.

## Theme

Use a light-first interface. Forest Black is for text, deep product objects, dashboards, and focused CTAs. The page background should mostly alternate between Cloud White and Soft Sandstone, with subtle gradients and brand imagery.

## Colour Tokens

- Forest Black: `#021111`
- Soft Sandstone: `#F2EFEB`
- Trending Turquoise: `#00CCDD`
- Cloud White: `#FAFAFD`
- Slate Grey: `#394141`
- Warm Grey: `#85888E`
- Pebble Grey: `#D5D8DB`
- Mist Grey: `#EAEBED`
- Pumpkin: `#FF8931`
- Honey: `#FFB21D`
- Green: `#078B12`
- Violet: `#8B1FD1`
- Red Orange: `#FF4318`

## Typography

Use Lufga when available. In this standalone build, use `Plus Jakarta Sans` as the geometric fallback. Keep headlines bold, short, and literal. Avoid negative letter spacing. Body copy should be calm, clear, and grounded.

## Layout

- First viewport must immediately show the Naar brand, the product promise, and an app-like object.
- Use full-width sections, not nested page cards.
- Cards are reserved for product, testimony, dashboard, and CTA objects.
- Default radius is 16px for content cards and 999px for pill actions.
- Keep fixed-format objects dimensioned with `min-height`, `aspect-ratio`, or explicit tracks so animation does not shift layout.

## Motion

- Motion should feel like a product demo, not decoration.
- Hero: brand reveal, particle field, image parallax, and floating phone.
- Problem: scroll-pinned contrast wipe from old commerce to Naar.
- Product: scroll-pinned phone rotation with synchronized labels.
- How it works: SVG path draw and staggered step reveal.
- Sellers: live dashboard ticker, bars, order rows, and toast.
- Creators: earnings counter, progress fills, and badges.
- Community: particle constellation forming the Naar mark.
- Closing: portal bloom and CTA reveal.
- Respect `prefers-reduced-motion`; never hide content unless JavaScript has enabled motion.

## Components

- Primary button: turquoise fill, Forest Black text.
- Secondary button: white translucent fill, Forest Black text, subtle border.
- App Store button: Forest Black fill on light surfaces.
- Navigation: light glass surface, dark Naar wordmark, compact links.
- Dashboard: Forest Black card on a light page to create focus.
- Imagery: use extracted brand-system assets from `naar-brand-assets/` before generic stock.

## Quality Guardrails

- Light theme must remain readable at desktop and mobile widths.
- Animation should not create blank first paint.
- Avoid one-colour palettes; turquoise must be balanced with sandstone, pumpkin, green, violet, and neutral grey.
- Do not add marketing-only sections unless they deepen the actual product journey.
- Validate with a desktop screenshot, a mobile screenshot, and a JavaScript syntax check before handoff.
