# Design System: kea (incident causality dashboard)

Source of truth for every UI contributor. The visual language is copied from the reference dashboard
the owner chose (context.dev usage and overview pages), with tokens read from its public CSS: **IBM Plex
Sans and IBM Plex Mono**, the Tailwind gray scale, one blue accent, 14px cards with a soft small shadow.
The topology graph follows the owner's Obsidian graph-view reference. Tools: `minimalist-ui`,
`design-taste-frontend`, `dataviz`, `emil-design-eng`, `redesign-existing-projects`,
`stitch-design-taste`. When a skill conflicts with the reference or with the product principles, the
reference and the principles win.

## 1. Visual theme and atmosphere
A calm, light, high-clarity operations dashboard. White cards float on a very light gray page; structure
comes from generous rounding, 1px hairlines and one soft shadow. Density is moderate-high (7/10) but
never cramped: 16px card padding, 16px gaps. Variance low (3/10, a predictable sidebar plus grid),
motion restrained (3/10). **Light is the default**; dark (`<html data-theme="dark">`) is a deep
blue-black with dark navy cards and no shadows.

## 2. Color roles (tokens live in `src/app/globals.css`, use the Tailwind names)
| Role | Light | Dark | Use |
|---|---|---|---|
| `bg` | #f7f7f8 | #0a0b10 | page |
| `surface` | #ffffff | #14161f | cards, panels |
| `surface-2` | #f3f4f6 | #1c1f2b | active tab pill, hover rows, recessed tracks |
| `line`, `line-strong` | #e5e7eb, #d1d5dc | #232736, #323750 | 1px borders |
| `text`, `text-2`, `text-3` | #101828, #4a5565, #6a7282 | #f3f4f6, #a3aab8, #7a8194 | primary, secondary, muted |
| `accent` | #2563eb | #6ea8ff | links, focus, selection |
| `btn` | #3080ff | #3080ff | primary button and progress fills, white text |
| `ok / warn / bad` | #067647 / #b54708 / #b42318 | #4ade9c / #fdb022 / #f97066 | **text and icons** (AA contrast) |
| `ok-fill / warn-fill / bad-fill` | #17b26a / #f79009 / #f04438 | #32d583 / #fdb022 / #f97066 | **dots, bars, node fills** |
| `f1..f4` | #2a78d6 #eb6834 #1baf7a #eda100 | #3987e5 #d95926 #199e70 #c98500 | factor series, fixed order (validated with the dataviz validator) |
Only health, severity and the four factor series use color besides the blue accent. No gradients,
no purple, no pure black or white text on backgrounds.

## 3. Typography
- **IBM Plex Sans** for everything: 14px body, 13px controls, 12px labels, 15px card titles, 26px stat
  values (medium), 30px page title (light 300, tracking -0.02em, centered).
- **IBM Plex Mono** (`.num`) for numbers, ids, times, Cypher, legends and small section pills.
- Sentence case. Uppercase only for the tiny Badge labels and mono section pills. No em-dashes or
  en-dashes in visible text. No emoji. No "seamless / elevate / unleash".

## 4. Components (all in `src/components/ui.tsx`)
- **Card / Panel:** white, 1px `line` border, 14px radius (`rounded-card`), `shadow-card` (none in dark).
- **CardHeader + IconTile:** a 40px icon inside four corner brackets, a 15px medium title, right-aligned
  metric or controls. Every card that shows data has one.
- **Segmented:** pill tabs, active = `surface-2` fill, inactive = muted text; arrow keys move selection.
- **StatCard:** label, 26px value, mono-free caption, optional thin progress bar (blue on `surface-2`).
- **Button:** 34px tall, 8px radius (`rounded-control`). Primary = blue fill, white text. Secondary =
  white with border and shadow. Ghost = text only. Press feedback scale(0.97) via `.pressable`.
- **Badge:** small pill with a soft tinted background and tone text. **SectionPill:** mono uppercase
  outlined label that names a group in the sidebar ("RUN", "VIEW").
- **LegendDot:** 6px dot plus mono text, as in the reference chart legends.
- **HealthChip:** icon + word + tone (never color alone).

## 5. Layout (1440x900 primary, no page scroll)
Left sidebar 248px (brand, RUN controls, VIEW nav, status card, theme switch). Content column: centered
page title and subtitle, a row of four stat cards, then a grid of [topology card over timeline card] and
[incident card 440px] that fills the rest. Long content scrolls inside its own card (`.scroll-quiet`).
Radii: cards 14, controls 8, pills full. Spacing scale 4/8/12/16/24.

## 6. Topology graph (Obsidian-style)
Round nodes sized by degree, filled with the health fill color, a soft halo, a white health icon inside,
the name and a health word beneath, thin neutral bezier edges with small arrowheads (non-blocking
dashed), a faint dot grid behind. Hover or focus a node to highlight its neighbors and dim the rest.
Fixed layout coordinates (deterministic), no physics, no pan or zoom.

## 7. Data visualization (dataviz)
Factor breakdown = one thin stacked bar (segment width = contribution, fixed order, 2px gaps, 4px round
ends) plus four labeled rows with `value x weight = contribution` in mono. Labels and values are always
visible (light aqua and yellow are under 3:1). Text never wears series colors. Status colors are
reserved and always carry an icon and a word.

## 8. Motion (emil-design-eng)
Only transform and opacity, 120-220ms, `--ease-out` or `--ease-drawer`, never ease-in, never
`transition: all`, never from scale(0). No animation on keyboard or high-frequency updates (timeline
rows, metric ticks, tab changes). Hover only under `@media (hover: hover)`. The one looping animation is
the causal-path pulse. Everything honors `prefers-reduced-motion`.

## 9. States and accessibility
Every surface has loading (skeleton in the final shape), empty (says how to populate), and error (inline)
states. WCAG AA in both themes, visible focus ring, keyboard access everywhere, meaningful icons carry a
text label. Product principles: scores are never probabilities (no percent, never "confidence"), every
LLM block is badged LIVE / REPLAYED / TEMPLATE, fixture replay shows a persistent banner.

## 10. Banned
Inter, serif faces, pure black, neon glows, gradients, emoji, hand-drawn icon paths, cards inside cards,
three-equal-column feature rows, generic names, fake round numbers, filler UI text.
