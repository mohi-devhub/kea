# kea UI design brief

Single source of truth for every UI contributor. Direction: **calm, dense, warm-monochrome ops
dashboard**, dark by default (projector demo), light via `<html data-theme="light">`.
Dials: variance 3, motion 3, density 7. Built from the `minimalist-ui`, `design-taste-frontend`,
`dataviz` and `emil-design-eng` skills, adapted for a dashboard (their landing-page composition
rules do not apply; their palette, restraint, state, motion and accessibility rules do).

## Non-negotiables (from UI_SPEC section 1, they beat any skill)
1. Scores are never a probability: show `0.82`, never a percent, never the word "confidence". Footnote:
   "Heuristic score, not a probability."
2. Every LLM-derived block has a `LIVE` / `REPLAYED` / `TEMPLATE` badge; fixture playback shows a
   persistent `FIXTURE REPLAY` banner.
3. Color is never the only signal: health = color + icon + text.
4. Ambiguity is shown ("Multiple plausible hypotheses", with the margin).
5. Everything shown is traceable: candidate -> factors -> chain -> evidence.

## Tokens (`src/app/globals.css`, use the Tailwind names: `bg-surface`, `text-text-2`, `border-line`)
- Surfaces: `bg` page, `surface` panels, `surface-2` raised or hovered. Text: `text`, `text-2`, `text-3`.
- Structure comes from 1px `border-line`. **No shadows, no gradients, no glass.** No pure black or white.
- One accent (`accent`, `accent-bg`) for selection, focus, links. Health and severity only use
  `ok / warn / bad` (+ `-bg`). Nothing else is colored.
- Radii, one system: cards and panels 8px (`rounded-card`), controls and inputs 6px
  (`rounded-control`), badges and health chips full. Buttons: solid `btn` on `btn-text`, no shadow.
- Type: Geist (UI) and Geist Mono (ids, scores, times, Cypher). Sizes 12 / 14 / 16 / 20. Numbers, ids,
  timestamps use the `.num` class (mono, tabular). Body 14px, labels 12px. No serif, no Inter.
- Icons: **Phosphor only** (`@phosphor-icons/react`), `weight="bold"`, size 14 or 16. Never hand-drawn
  SVG paths, never emoji, never Lucide.
- Copy: plain and specific. **No em-dashes or en-dashes in visible text** (use a hyphen, comma or period).
  No "seamless / elevate / unleash". Sentences a stranger understands ("Healthy until 10:05:40").

## Layout (1440x900 primary, 1920x1080 secondary, no page scroll)
Header 48px. Body is a grid: left column (topology graph fills, timeline fixed 240px) and right column
(incident panel 480px, scrolls inside itself with `.scroll-quiet`). Panels are `bg-surface` with a 1px
border and 8px radius, 12px gap between them. Density is high: 12px labels, 8 and 12px paddings inside
cards (16px only on the outer panel), hairline dividers instead of nested boxes. Never a card inside a
card; group with `border-t` and spacing.

## Data visualization (dataviz skill)
- **Factor breakdown** is one thin horizontal stacked bar per candidate: four segments whose widths are
  each factor's `contribution`, in fixed order (timing `--f1`, explains `--f2`, strength `--f3`, impact
  `--f4`), 2px surface gaps between segments, 4px rounded ends, total = the score, printed as `0.82`.
  Under it, four rows: color swatch, label, `value x weight = contribution` in mono. Labels and values
  are always visible (the light-theme aqua and yellow are under 3:1, so this is required). The palette
  was run through `validate_palette.js` for both themes; do not swap colors without re-running it.
- Text wears text tokens, never the series color. Status colors are reserved for health and verdicts and
  always ship with an icon and a word.
- Sparklines or counters (P2 charts) use one hue, 2px line, no fill, no grid.
- Tooltips and hover: every mark with a value has a hover or focus tooltip; hit targets bigger than marks.

## Motion (emil-design-eng)
- Animate only `transform` and `opacity`. Durations 120-220ms, UI easing `var(--ease-out)`. Never ease-in,
  never `transition: all`, never `scale(0)` (start at 0.95 with opacity).
- Never animate keyboard-initiated or high-frequency things (timeline row arrivals, tab switches,
  metric ticks). Panels and drawers: 200ms `--ease-drawer`. Popovers are origin-aware.
- Press feedback: add the `.pressable` class to every button (scale 0.97 on press). Hover styles live in
  `@media (hover: hover)` only.
- The **only** looping animation is the causal-path pulse (`.kea-pulse`). Everything honors
  `prefers-reduced-motion` (globals already collapse durations; pulse becomes static emphasis).
- Use CSS transitions (interruptible), not keyframes, for state changes.

## States (every surface needs all of them)
Loading = skeleton in the final shape (no spinners for panels). Empty = a sentence that says how to
populate it ("Pick a scenario and press Start."). Error = inline and contextual, toasts only for transient
failures. Disconnected = a banner "Reconnecting...".

## Accessibility
WCAG AA text contrast in both themes. Visible `:focus-visible` ring (global). All controls reachable by
keyboard; graph nodes are buttons with accessible names ("payment, failing"). Icons that carry meaning
have text beside them or an `aria-label`. Respect reduced motion. No hover-only information.

## Definition of done for a component
Both themes checked. Keyboard path works. Empty, loading and error states exist. No em-dash, emoji,
percent-on-score, or the word "confidence". `pnpm lint` and `pnpm typecheck` clean. No `any` in
contract types. No `setState` on a hot path that re-renders the graph (metric batches must not).
