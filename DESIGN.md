# SECFEDCLAW Design System

Version: v0.2 · Generated from live dashboard CSS · Updated 2026-06-09

**Design philosophy:** Federal-grade authority without visual noise.
The dashboard is an APP UI — data-dense, task-focused, offline-capable.
Every design decision defers to USWDS (designsystem.digital.gov) and
SEC.gov's navy palette. No decorative elements earn their pixels.

---

## Color Tokens

All colors are CSS custom properties on `:root`. Never use hardcoded hex
in new components — always reference a token.

### Surface hierarchy
| Token | Value | Use |
|---|---|---|
| `--bg` | `#ffffff` | Primary surface (page, cards, table rows) |
| `--panel` | `#f0f0f0` | Secondary surface (table headers, input bg) |
| `--panel-2` | `#e8f0f8` | Tertiary surface (explanation blocks, active states) |

### Borders
| Token | Value | Use |
|---|---|---|
| `--line` | `#dfe1e2` | Default border (cards, table row dividers) |
| `--line-2` | `#a9aeb1` | Stronger border (table header, focus rings) |

### Text
| Token | Value | Use |
|---|---|---|
| `--ink` | `#1b1b1b` | Primary text (USWDS base-ink) |
| `--muted` | `#555f6b` | Secondary text (intros, labels, table headers) |
| `--faint` | `#71767a` | Tertiary text (metadata, footnotes) |

### Brand (USWDS blue-60v + SEC.gov navy)
| Token | Value | Use |
|---|---|---|
| `--brand` | `#005ea2` | Primary interactive (links, active tabs, KPI numbers) |
| `--brand-dark` | `#1a4480` | Hover/pressed states |
| `--brand-light` | `#d9e8f6` | Background tints (explanation blocks, hover rows) |
| `--accent` | `#c9a227` | Gold accent (header bottom border — SEC identity) |
| `--header-bg` | `#17375e` | Header background (SEC.gov navy) |
| `--header-ink` | `#ffffff` | Header text |

### Semantic status (USWDS)
| Token | Value | Use |
|---|---|---|
| `--ok` | `#00a91c` | Success green (score bar fills, .dot.ok) |
| `--crit` | `#b50909` | Critical error red (CRITICAL_REVIEW priority) |
| `--high` | `#c05600` | Warning amber (HIGH priority) |
| `--med` | `#276130` | Medium green (MEDIUM priority) |
| `--low` | `#555f6b` | Low/muted (LOW priority) |

### Semantic backgrounds (paired with above)
| Token | Value | Use |
|---|---|---|
| `--ok-bg` | `#ecf3ec` | Success background |
| `--crit-bg` | `#fff3ee` | Critical background |
| `--high-bg` | `#fef0e8` | Warning background |
| `--med-bg` | `#edf5ee` | Medium background |
| `--low-bg` | `#f0f0f0` | Low background (= `--panel`) |

---

## Typography

**Primary stack:** `"Public Sans", "Source Sans Pro", -apple-system, system-ui, sans-serif`

Public Sans is the USWDS default. If unavailable (offline deployment), Source
Sans Pro or the system sans-serif renders acceptably at this font stack.
Do not use `-apple-system` or `system-ui` as the PRIMARY display font — they
are the "I gave up on typography" signal and are only fallbacks here.

| Role | Size | Weight | Token reference |
|---|---|---|---|
| Body | 16px | 400 | `font:16px/1.6 var(--f)` |
| Intro / contextual | 16px | 400 | `.intro` — same as body, muted color |
| H2 section heading | 22px | 700 | `h2` |
| H3 card/table heading | 17px | 700 | `h3` — 1px above body for scan-ability |
| Small / metadata | 13px | 400 | `.small` |
| Label / caption | 11.5–12px | 600–700 | `thead th`, `.kpi-lbl` |
| Ref link pills | 10.5px | 700 | `.reflinks a` |

**Scale rule:** Body (16) → H3 (17) → H2 (22). Not a strict ratio but each
level is unambiguously larger. Do not add heading levels that collapse to body size.

---

## Spacing Scale

Base: **4px**. All spacing values are multiples of 4px via CSS variables.

| Token | Value | Use |
|---|---|---|
| `--s1` | 4px | Icon gaps, tight inline spacing |
| `--s2` | 8px | Internal card padding (small), row gaps |
| `--s3` | 12px | Card padding (standard), heading margin-bottom |
| `--s4` | 16px | Section padding, button padding |
| `--s5` | 24px | Panel padding (`.wrap`), section gaps |
| `--s6` | 32px | Large section separators |

**Rule:** Never use magic-number pixel values in new CSS. Pick the nearest
scale token. `10px` → use `--s2` (8px) or `--s3` (12px).

---

## Border Radius

`--radius: 4px` — USWDS minimal. Applied consistently to cards, buttons,
tabs, and pills, EXCEPT:

- `.pill` uses `border-radius: 99px` for pill-badge shape (intentional, not slop)
- `.info` (tooltip trigger) uses `border-radius: 50%` for the circular ⓘ badge

Do not introduce new large radii (8px+). The system reads clean precisely because
every element uses the same 4px radius.

---

## Shadow

`--shadow: 0 1px 3px rgba(0,0,0,.12)` — single subtle drop shadow for cards
and KPI tiles. Do not add larger/more dramatic shadows; they contradict the
federal / minimal aesthetic.

---

## Component Inventory

### Header (`.topbar`)
- Background: `--header-bg` (#17375e SEC navy)
- Bottom border: 4px solid `--accent` (#c9a227 gold) — SEC identity
- Position: sticky top:0, z-index:10
- Contains: brand name, subtitle, metadata right-aligned, `.boundary` warning

### Government banner (`.govbanner`)
- Background: `--panel` (#f0f0f0)
- Text: 12px, `--muted`
- Above the header — USWDS "official website" pattern

### Sidebar navigation (`.sidebar`)
- Fixed left, full height
- Background: `--header-bg` (matches header — one continuous left edge)
- Right border: 3px solid `--accent` (gold accent continues down)
- Expanded: 220px. Collapsed: 48px.
- Toggle button: minimum 44×44px touch target, :focus-visible ring

### Tabs (`.tab`)
- Vertical list inside sidebar
- Inactive: rgba(255,255,255,.7) text on navy
- Active: rgba(255,255,255,.18) background, white text, rgba border
- Collapsed icons: single letter via CSS `::before content`

### Cards (`.card`)
- Background: `--bg` (white)
- Border: 1px solid `--line`
- Radius: `--radius` (4px)
- Shadow: `--shadow`
- No colored left-borders on data cards

### KPI tiles (`.kpi`)
- Top accent: 3px solid `--brand` (blue top border signals interactivity/data)
- Numeric values: 24px/700 in `--brand`
- String/status values: 15px/600 in `--muted` (`.kpi-num.kpi-text`)
- Label: 12px uppercase, `--muted`

### Priority pills (`.pill`)
- Radius: 99px (intentional pill shape)
- Four variants using semantic token pairs:
  - `.crit`: `--crit` on `--crit-bg`
  - `.high`: `--high` on `--high-bg`
  - `.med`: `--med` on `--med-bg`
  - `.low`: `--low` on `--low-bg`

### Tables (USWDS usa-table)
- `thead th`: `--panel` background, `--muted` 11.5px uppercase, 2px bottom border
- `tbody tr:hover`: `#f5f7fb` (light blue-tinted hover)
- Numeric columns: `font-variant-numeric: tabular-nums`, right-aligned

### Filter buttons (`.filters button`)
- Minimum height: 32px
- Default: `--bg` with `--line-2` border
- Hover: `--brand-light` bg, `--brand` border and text

### Score bars (`.bar`)
- Background: `--panel`
- Fill colors: green gradient (`#00571a → #00a91c`) for evidence scores
- Anomaly fill: amber gradient (`#7a2700 → #c05600`)
- Bar text: white with `text-shadow:0 0 3px rgba(0,0,0,.5)` for contrast

### Explanation blocks (`.expl`)
- Background: `--brand-light` (#d9e8f6 light blue)
- Border: 1px solid `rgba(0,94,162,.15)` (subtle brand-tinted)
- No left-border accent (removed — was AI slop pattern #8)

### Status dots (`.dot`)
- 9px circle, no text label — decorative only
- `.ok` green, `.warn-d` amber, `.bad` red, `.idle` gray

### Tooltip (`.info` / `.tooltip`)
- Trigger: 17×17px circle, `--brand` background, white ⓘ
- `tabindex="0"` + `aria-label` — keyboard accessible
- Shows on `:hover` and `:focus-visible` (not bare `:focus`)
- Tooltip itself: `pointer-events:none`

---

## Accessibility

- Body text: 16px minimum, `--ink` (#1b1b1b) on white → 17.5:1 contrast
- Muted text: `--muted` (#555f6b) on white → 5.6:1 (WCAG AA ✓)
- `color-scheme: light` declared on `<html>`
- `focus-visible` rings on all interactive elements
- ARIA labels on ⓘ tooltip triggers and sidebar toggle
- Priority pills carry text + color (not color-only encoding)
- Reduced-motion: tab panel animation uses `opacity` only (no layout)

---

## AI Slop Blacklist — Patterns Removed

These patterns were present and have been removed. Do not re-introduce.

| Pattern | Status |
|---|---|
| `-apple-system` as primary font | Removed — Public Sans is primary |
| 12px bubble border-radius everywhere | Removed — 4px throughout |
| GitHub-dark background (#0d1117) | Removed — USWDS white |
| Colored left-border on `.expl` cards | Removed — background alone suffices |
| Dark-themed priority pills (dark bg, light text) | Removed — semantic USWDS colors |

---

## Responsive

Single breakpoint: `max-width: 760px`

- Sidebar auto-collapses to 48px (icon-only)
- `.page-shell` margin adjusts automatically
- `.grid2` stacks to single column
- `.cases`, `.pipeline` stages stack vertically
- Arrow elements (`.arrow`) hidden on mobile

---

## Do / Don't

**Do:**
- Use CSS variable tokens for every color and spacing value
- Add new component classes following the existing naming conventions
- Keep cards white with `--line` border and 4px radius
- Use `--brand` (#005ea2) for interactive/data emphasis
- Use `--header-bg` (#17375e) for navigation chrome

**Don't:**
- Add gradients to backgrounds (the navy header gradient is the only permitted one)
- Use `text-align: center` on data content (only icons, footer)
- Add decorative elements (blobs, dividers, icons-in-circles)
- Use purple, violet, or indigo anywhere
- Add border-left accents to data cards
- Use `transition: all` (list specific properties)
