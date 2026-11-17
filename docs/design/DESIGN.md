---
name: Travel CRM Workspace
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#3f484c'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#6f787d'
  outline-variant: '#bec8cd'
  surface-tint: '#006781'
  primary: '#005a71'
  on-primary: '#ffffff'
  primary-container: '#0e7490'
  on-primary-container: '#d3f1ff'
  inverse-primary: '#81d1f0'
  secondary: '#006399'
  on-secondary: '#ffffff'
  secondary-container: '#7bc2ff'
  on-secondary-container: '#004f7b'
  tertiary: '#005785'
  on-tertiary: '#ffffff'
  tertiary-container: '#0070aa'
  on-tertiary-container: '#dfeeff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#b9eaff'
  primary-fixed-dim: '#81d1f0'
  on-primary-fixed: '#001f29'
  on-primary-fixed-variant: '#004d62'
  secondary-fixed: '#cde5ff'
  secondary-fixed-dim: '#94ccff'
  on-secondary-fixed: '#001d32'
  on-secondary-fixed-variant: '#004b74'
  tertiary-fixed: '#cce5ff'
  tertiary-fixed-dim: '#93ccff'
  on-tertiary-fixed: '#001d31'
  on-tertiary-fixed-variant: '#004b73'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-xs:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-xs:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-compact: 0.5rem
  margin: 1.5rem
  margin-mobile: 0.75rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system delivers a calm, high-density, analytical workspace tailored for travel managers, tour operators, and agency coordinators managing high-velocity client bookings, complex multi-leg itineraries, and financial reconciliations. 

The aesthetic is grounded in modern B2B clarity, drawing direct influence from Linear, Stripe Dashboard, and Notion:
- **Calm Authority & Precision:** Eliminates visual noise and decorative bloat in favor of high-yield data ergonomics, clear status stratification, and typographic hierarchy.
- **High-Density Utility:** Compact component height metrics and snug gutters allow agents to view end-to-end trip lifecycles, ledger records, and customer communications without unnecessary scrolling.
- **Tactile Soft-Flat Finish:** Restrained use of elevation, relying on precise 1px micro-borders (`#E2E8F0`), subtle surface tinting (`#F8FAFC`, `#F1F5F9`), and controlled 6–8px corner radii.

## Colors

The palette leverages oceanic slate and deep cyan hues to communicate stability and efficiency, coupled with an extensive neutral slate scale and dedicated four-pillar status matrices designed to maintain visual independence across concurrent workflow states.

### Core Swatches
- **Primary (`#0E7490`):** Deep oceanic cyan. Primary action buttons, active navigation markers, keyboard focus outlines.
- **Secondary (`#0369A1`):** Deep maritime blue. Secondary highlights, filtering criteria, interactive metadata links.
- **Tertiary (`#0284C7`):** Vivid sky cyan. Informational indicators, subtle timeline checkpoints, selection badges.
- **Neutral Base (`#0F172A`):** Deep midnight slate for primary typography, dominant structural chrome, and high-emphasis labels.

### Surface & Border Foundations
- `surface-app`: `#F8FAFC` (Canvas background)
- `surface-card`: `#FFFFFF` (Card panels, table rows, drawer containers)
- `surface-subtle`: `#F1F5F9` (Sub-headers, table header tracks, code/tag wells)
- `surface-active`: `#E2E8F0` (Hovered lists, table striping, borders)
- `text-primary`: `#0F172A` (900 slate, WCAG AAA against white)
- `text-secondary`: `#475569` (600 slate, supporting labels, table metadata)
- `text-muted`: `#64748B` (500 slate, helper hints, timestamps)
- `border-default`: `#E2E8F0` (Standard panel and cell dividers)
- `border-focus`: `#0E7490` (Input focus and selected state indicators)

### Status Architecture (WCAG AA Compliant)
To prevent cross-entity confusion across concurrent processes on a single itinerary screen, statuses are assigned strict color channels:

1. **Application Status (Inquiry Pipeline):**
   - *New:* `#4338CA` text on `#EEF2FF` background (Indigo)
   - *Under Review:* `#6D28D9` text on `#F5F3FF` background (Purple)
   - *Converted:* `#047857` text on `#ECFDF5` background (Emerald)
   - *Archived:* `#475569` text on `#F1F5F9` background (Slate)

2. **Booking Status (Voucher & Flight Confirmations):**
   - *Draft:* `#64748B` text on `#F8FAFC` background (Slate)
   - *Pending Partner:* `#B45309` text on `#FFFBEB` background (Amber)
   - *Confirmed:* `#0E7490` text on `#ECFEFF` background (Cyan)
   - *Cancelled:* `#BE123C` text on `#FFF1F2` background (Rose)

3. **Payment Status (Receivables & Invoicing):**
   - *Unpaid:* `#B91C1C` text on `#FEF2F2` background (Red)
   - *Partially Paid:* `#C2410C` text on `#FFF7ED` background (Orange)
   - *Paid in Full:* `#15803D` text on `#F0FDF4` background (Green)
   - *Overdue:* `#991B1B` text on `#FEE2E2` background (Crimson)

4. **Refund Status (Adjustments & Cancellations):**
   - *None:* `#94A3B8` text on `#F8FAFC` background (Muted Slate)
   - *Requested:* `#A16207` text on `#FEFCE8` background (Yellow)
   - *Processing:* `#0369A1` text on `#F0F9FF` background (Sky)
   - *Completed:* `#0F766E` text on `#F0FDFA` background (Teal)

## Typography

The typography structure centers on `Inter` (with system font fallbacks) configured for high legibility across dense data grids, financial totals, and multi-field forms.

- **Base Calibration:** The core UI operates on a `14px` base (`body-md`) with a strict `20px` line height, yielding a standardized vertical rhythm.
- **Numbers & Currencies:** Tabular figures (`font-variant-numeric: tabular-nums`) must be applied globally to table cells, financial aggregations, and exchange rate metrics to avoid misalignments during value updates.
- **Monospace Elements:** Use `JetBrains Mono` at `12px` for reservation locator codes (PNR), booking reference IDs, and flight segment tags.
- **Micro Labels:** `label-xs` uses uppercase casing with `+0.04em` letter spacing for section kickers, table column headers, and multi-currency tag labels.

## Layout & Spacing

The layout is constructed on a strict 4px/8px modular scale engineered for information-dense multi-column desk layouts.

### Structural Shell & Grid
- **Workspace Canvas:** Uses a fluid layout framed by a persistent collapsible navigation sidebar (240px expanded, 56px collapsed) and an optional contextual flyout inspector drawer (380px fixed width).
- **Primary Grid:** 12-column fluid grid system with `1rem` (16px) gutters on desktop, compressing to `0.5rem` (8px) within compact modal windows and split-view master-detail setups.
- **Canvas Margins:** Fixed `1.5rem` (24px) outer margin on desktop views (`>= 1024px`), reducing to `0.75rem` (12px) on mobile viewports.

### Breakpoints & Adaptive Flow
- **Desktop (>= 1280px):** 3-pane orchestration: Side Navigation, Main Workspace Table / Itinerary Board, Contextual Detail Drawer.
- **Laptop / Tablet Landscape (1024px - 1279px):** 2-pane mode: Collapsed navigation icon rail, responsive table with horizontal overflow scrolling, drawer transitions into an overlay modal.
- **Mobile (< 768px):** Single-column stacked layout; data tables swap to grouped summary cards; filter bars compress into an off-canvas drawer.

## Elevation & Depth

To maintain visual discipline and prevent visual fatigue during 8-hour agent shifts, depth is created predominantly through crisp 1px borders and surface color differentiation rather than heavy drop shadows.

- **Level 0 (Base Canvas):** Background tone `#F8FAFC`. Zero elevation, zero shadow.
- **Level 1 (Cards, Work Tables, Sub-bars):** Background tone `#FFFFFF`, encapsulated by a 1px border of `#E2E8F0`. Shadow: `0 1px 2px 0 rgba(15, 23, 42, 0.04)`.
- **Level 2 (Popovers, Select Menus, Filter Dropdowns):** Background `#FFFFFF`, border `#E2E8F0`. Shadow: `0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.04)`.
- **Level 3 (Slide-over Drawers, Floating Action Trays):** Border `#E2E8F0`. Shadow: `0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.03)`.
- **Level 4 (Modal Dialogs):** Centered overlay on backdrop `rgba(15, 23, 42, 0.45)`. Shadow: `0 20px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.04)`.

## Shapes

The geometric vocabulary matches contemporary desktop software standards, maintaining a unified 6px–8px radius rhythm (`roundedness: 2` scale) that looks engineered and clean.

- **Micro Controls (Badges, Checkboxes, Micro-inputs):** `4px` radius (`rounded-sm`).
- **Standard Controls (Inputs, Select triggers, Buttons, Tag chips):** `6px` radius (`rounded-md`).
- **Cards, Panels, Floating Sheets, Table Wrappers:** `8px` radius (`rounded-lg`).
- **Pills (Strictly restricted to count badges & quick-filter avatars):** `9999px` (`rounded-full`).

## Components

Custom configuration and styling rules tailored for Naive UI (`naive-ui 2.x`) inside Vue 3.

### Buttons (`NButton`)
- **Primary:** Background `#0E7490`, text `#FFFFFF`, border `transparent`. Hover: `#0369A1`. Height: `32px` default, `28px` compact. Font size: `13px`, medium weight.
- **Secondary / Default:** Background `#FFFFFF`, text `#0F172A`, border `1px solid #E2E8F0`. Hover: `#F1F5F9` background, border `#CBD5E1`.
- **Ghost / Subtle:** Background `transparent`, text `#475569`, border `none`. Hover: `#F1F5F9` background, text `#0F172A`.

### Status Badges & Chips (`NTag`)
- Compact height (`22px`), `4px` radius, `11px` font size, bold tracking (`0.02em`).
- Rendered in a borderless soft-surface finish (e.g. Booking Confirmed: background `#ECFEFF`, text `#0E7490`).
- Strict grouping: Always include the entity category prefix or icon when multiple statuses are shown in a single card (e.g., `Pay: Paid in Full` vs `Book: Confirmed`).

### Data Tables (`NDataTable`)
- Header row height `34px`, background `#F8FAFC`, uppercase `11px` column labels with color `#64748B`.
- Body row height `40px` (dense mode) or `48px` (default). Cell horizontal padding `12px`.
- Cell dividers: `1px solid #F1F5F9`. Hover row highlight: `#F8FAFC`.
- All financial, passenger count, and date values must use tabular numerals.

### Input Fields & Selects (`NInput`, `NSelect`, `NDatePicker`)
- Input height `32px`, font size `13px`, background `#FFFFFF`.
- Default border `1px solid #E2E8F0`, rounded to `6px`.
- Active / Focus: border `#0E7490`, glow `0 0 0 1px #0E7490`.
- Placeholder color: `#94A3B8`.

### Cards & Panels (`NCard`)
- Clean white surface `#FFFFFF`, border `1px solid #E2E8F0`, corner radius `8px`.
- Header separator: `1px solid #F1F5F9` with explicit `12px 16px` padding.
- Card actions footer: soft background `#F8FAFC` separated by `1px solid #E2E8F0`.

### Itinerary Segment Cards (Specialized Component)
- Nested border style (`1px solid #E2E8F0`) with a `3px` colored left-spine indicator signifying mode of transit (Flight: `#0369A1`, Hotel: `#0E7490`, Transfer: `#6366F1`, Train: `#059669`).