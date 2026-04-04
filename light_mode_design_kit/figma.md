# InboxIQ Design Kit

## Brand Direction

InboxIQ should feel calm, intelligent, trustworthy, and operational.

**Design keywords:** Clean · Focused · Professional · AI-assisted, not gimmicky · Human control and trust · Modern B2B SaaS

---

## Core Color System

### Neutrals

Use these for layout, text, borders, and surfaces.

| Token      | Hex       | Usage                                                             |
|------------|-----------|-------------------------------------------------------------------|
| slate-950  | `#020617` | Primary headings, dark sections, primary CTA text on light surfaces |
| slate-900  | `#0f172a` | Strong text, navigation                                           |
| slate-800  | `#1e293b` | Hover state for dark buttons                                      |
| slate-600  | `#475569` | Body text                                                         |
| slate-500  | `#64748b` | Secondary text                                                    |
| slate-400  | `#94a3b8` | Muted text on light backgrounds                                   |
| slate-300  | `#cbd5e1` | Muted text on dark backgrounds                                    |
| slate-200  | `#e2e8f0` | Borders, dividers                                                 |
| slate-100  | `#f1f5f9` | Soft section background                                           |
| slate-50   | `#f8fafc` | App/page base background                                          |
| white      | `#ffffff` | Card backgrounds                                                  |

### Primary Accent

Use for primary highlights and trusted AI/product signals.

| Token       | Hex       | Usage                                    |
|-------------|-----------|------------------------------------------|
| indigo-600  | `#4f46e5` | Accent text, badges, links, active states |
| indigo-200  | `#c7d2fe` | Accent borders                           |
| indigo-50   | `#eef2ff` | Accent card background, hero tint        |

### Secondary Accent

Use sparingly for complementary highlights.

| Token     | Hex       | Usage                     |
|-----------|-----------|---------------------------|
| cyan-700  | `#0e7490` | Secondary accent text     |
| cyan-600  | `#0891b2` | Secondary icon/accent     |
| cyan-50   | `#ecfeff` | Secondary accent background |

### Success / Automation / Safe Execution

Use for approval, success, safe automation, positive audit states.

| Token        | Hex       | Usage                        |
|--------------|-----------|------------------------------|
| emerald-900  | `#064e3b` | Success headings             |
| emerald-800  | `#065f46` | Success text                 |
| emerald-600  | `#059669` | Success icons/checks         |
| emerald-200  | `#a7f3d0` | Success borders              |
| emerald-50   | `#ecfdf5` | Success panels               |

### Warning / Priority / Urgency

Use for urgency or caution, but not error states.

| Token     | Hex       | Usage                        |
|-----------|-----------|------------------------------|
| amber-600 | `#d97706` | Warning icon/accent          |
| amber-50  | `#fffbeb` | Warning background           |
| rose-600  | `#e11d48` | Urgent / danger-lite accent  |
| rose-50   | `#fff1f2` | Urgent / priority background |

---

## Background Rules

### Page Backgrounds

| Purpose                        | Value     |
|-------------------------------|-----------|
| Default app/page background    | `#f8fafc` |
| Alternate section background   | `#f1f5f9` |
| Primary white content surface  | `#ffffff` |
| Dark emphasis section          | `#020617` |

### Hero Gradient

Use a soft gradient **only** in hero or special highlighted zones.

```
#eef2ff → #ffffff → #ecfeff
```

> Do not use loud gradients in the app workspace.

---

## Typography

### Font Stack

Use a clean sans serif:

```
Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI
```

### Heading Scale

| Style       | Size            | Weight | Usage                        |
|-------------|-----------------|--------|------------------------------|
| Display XL  | 60px / 3.75rem  | 700    | Hero headline                |
| Display L   | 48px / 3rem     | 700    | Large section headings       |
| H1/Hero alt | 40px / 2.5rem   | 700    | Secondary hero heading       |
| H2          | 36px / 2.25rem  | 700    | Main section headings        |
| H3          | 24px / 1.5rem   | 600    | Card titles                  |
| H4          | 20px / 1.25rem  | 600    | Smaller section/card headings |
| Body L      | 20px / 1.25rem  | 400    | Hero/body intro              |
| Body        | 16px / 1rem     | 400    | Standard content             |
| Small       | 14px / 0.875rem | 400    | Secondary text               |
| XS label    | 12px / 0.75rem  | 600    | Eyebrow labels, overlines    |

### Text Color Rules

- **Headings:** `#020617`
- **Body text:** `#475569`
- **Secondary text:** `#64748b`
- **Dark section text:** `#cbd5e1` and `#94a3b8`

---

## Spacing System

Use a 4px base scale.

| Token    | Value |
|----------|-------|
| space-1  | 4px   |
| space-2  | 8px   |
| space-3  | 12px  |
| space-4  | 16px  |
| space-5  | 20px  |
| space-6  | 24px  |
| space-8  | 32px  |
| space-10 | 40px  |
| space-12 | 48px  |
| space-16 | 64px  |
| space-20 | 80px  |
| space-24 | 96px  |

### Layout Rhythm

- Card internal padding: `24px` or `32px`
- Section vertical padding: `64px` to `96px`
- Card gap in grids: `24px`
- Page max width: `1280px`

---

## Border Radius System

| Token       | Value  | Usage                      |
|-------------|--------|----------------------------|
| radius-sm   | 12px   | Pills, small chips         |
| radius-md   | 16px   | Buttons, inputs            |
| radius-lg   | 24px   | Cards                      |
| radius-xl   | 28px   | Hero cards / premium panels |
| radius-pill | 9999px | Badges, pills              |

**Tailwind mapping:** `rounded-xl` · `rounded-2xl` · `rounded-3xl` · `rounded-[28px]`

---

## Card System

### Standard Feature Card

Use for features, value props, integrations.

| Property   | Value              |
|------------|--------------------|
| Background | `#ffffff`          |
| Border     | `1px solid #e2e8f0` |
| Radius     | 24px               |
| Padding    | 24px               |
| Shadow     | Soft only          |
| Title size | 24px               |
| Body text  | 14px–16px          |
| Min height | 220px–260px        |

### Highlight Card

Use for proof, workflows, smart actions, examples.

| Property   | Value              |
|------------|--------------------|
| Background | `#ffffff`          |
| Radius     | 28px               |
| Padding    | 28px–32px          |
| Border     | `1px solid #e2e8f0` |
| Shadow     | Medium-soft        |
| Min height | 320px+             |

### Status Card

Use for results, success, approval, audit.

| Property   | Value              |
|------------|--------------------|
| Background | `#ecfdf5`          |
| Border     | `1px solid #a7f3d0` |
| Radius     | 16px–24px          |
| Padding    | 16px–20px          |

### Dark Emphasis Card

Use sparingly.

| Property   | Value                         |
|------------|-------------------------------|
| Background | `#020617`                     |
| Text       | `#ffffff`, `#cbd5e1`, `#94a3b8` |
| Radius     | 28px                          |
| Padding    | 32px                          |

---

## Button System

### Primary Button

| Property   | Value     |
|------------|-----------|
| Background | `#020617` |
| Text       | `#ffffff` |
| Hover      | `#1e293b` |
| Radius     | 16px      |
| Padding    | 12px 24px |
| Weight     | 600       |
| Shadow     | Subtle    |

### Secondary Button

| Property   | Value              |
|------------|--------------------|
| Background | `#ffffff`          |
| Border     | `1px solid #cbd5e1` |
| Text       | `#334155`          |
| Hover bg   | `#f8fafc`          |
| Radius     | 16px               |
| Padding    | 12px 24px          |

### Ghost / Tertiary Button

| Property   | Value                      |
|------------|----------------------------|
| Background | Transparent                |
| Text       | `#4f46e5` or `#334155`     |
| Hover bg   | `#eef2ff` or `#f8fafc`     |

---

## Badge and Chip System

Use for trust signals, categories, filters, AI states.

### Standard Badge

| Property   | Value                |
|------------|----------------------|
| Background | `#ffffffcc`          |
| Border     | `1px solid #c7d2fe`  |
| Text       | `#4f46e5`            |
| Radius     | Pill                 |
| Padding    | 8px 16px             |
| Font size  | 14px                 |

### Neutral Chip

| Property      | Value       |
|---------------|-------------|
| Background    | `#ffffffcc` |
| Ring/border   | `#e2e8f0`   |
| Text          | `#64748b`   |

---

## Shadow System

Use subtle shadows only.

| Token         | Value                                                                  | Usage              |
|---------------|------------------------------------------------------------------------|--------------------|
| shadow-soft   | `0 1px 2px rgba(15,23,42,0.04), 0 8px 24px rgba(15,23,42,0.06)`       | Basic cards        |
| shadow-medium | `0 10px 30px rgba(15,23,42,0.10)`                                      | Highlight cards    |
| shadow-large  | `0 20px 50px rgba(15,23,42,0.12)`                                      | Hero feature panels |

> Avoid harsh shadows and neon glow.

---

## Icon System

Use SVG icons instead of emoji in production.

### Style

- 24px outline SVG icons
- 1.75–2 stroke weight
- Rounded ends/joints
- Clean geometric style

**Recommended libraries:** Lucide · Heroicons · Tabler Icons

### Standard Sizes

| Size  | Usage               |
|-------|---------------------|
| 16px  | Inline labels       |
| 20px  | Buttons / chips     |
| 24px  | Card icons          |
| 28px  | Highlight cards     |
| 32px  | Section emphasis    |

### Icon Containers (Tinted Tiles)

| Property   | Value                                           |
|------------|-------------------------------------------------|
| Size       | 48px × 48px                                     |
| Radius     | 16px                                            |
| Background | Tint: `#eef2ff`, `#ecfeff`, `#ecfdf5`, `#fff1f2` |
| Icon color | Corresponding accent color                      |

### InboxIQ Feature → Icon Mapping

| Feature              | Suggested Icon                          |
|----------------------|-----------------------------------------|
| Email classification | Inbox / Mail / AtSign                   |
| Urgency detection    | AlertCircle / Siren / TriangleAlert     |
| Routing              | Compass / Route / GitBranch             |
| Draft replies        | PencilLine / PenSquare                  |
| Human review         | ShieldCheck / UserCheck / Scale         |
| Automation           | Cog / Zap / Workflow                    |
| Approval policy      | Shield / BadgeCheck / Lock              |
| Audit trail          | FileCheck / ClipboardList / History     |
| Calendar scheduling  | Calendar / CalendarClock                |
| Gmail integration    | Mail / Inbox                            |
| Outlook integration  | CalendarDays / Briefcase                |

### SVG Rules

- Use stroke-based SVGs for consistency
- Keep strokes rounded
- Do not mix filled cartoon icons with outline icons
- Avoid more than 2 icon colors in one component
- Use `currentColor` where possible for easy theming

**Recommended SVG attributes:**

```svg
fill="none"
stroke="currentColor"
stroke-width="1.75"
stroke-linecap="round"
stroke-linejoin="round"
```

---

## Section Templates

### Hero Section

- Background: hero gradient
- Layout: 2-column
- Left: badge, headline, supporting text, CTAs, trust chips
- Right: highlight card / product outcome panel
- Vertical padding: 80px–96px

### Pain Section

- Background: `#f1f5f9`
- Heading centered
- 3 cards in a row on desktop
- Use icon tiles and concise copy

### Feature Grid Section

- Background: `#ffffff`
- Heading centered
- 3-column grid on large screens
- Standard cards with icons

### Dark Trust Section

- Background: `#020617`
- White heading, muted support text
- Use sparingly for emphasis only

### CTA Section

- Background: `#020617`
- Heading centered
- Two buttons max — one primary, one secondary

---

## App UI Component Sizing

| Component               | Spec                                |
|-------------------------|-------------------------------------|
| Top nav                 | Height: 72px–80px                   |
| Sidebar                 | Width: 260px–300px                  |
| Main content cards      | Padding: 24px · Radius: 24px        |
| Thread / email cards    | Padding: 16px–20px · Radius: 16px · Border: `#e2e8f0` |
| AI suggestion panel     | Radius: 24px · Padding: 24px–28px   |
| Data chips / labels     | Height: 32px–36px · Radius: pill · Font: 13px–14px |

---

## Design Rules for Consistency

### Do

- Use the slate palette as the foundation
- Use indigo as the main intelligence/product accent
- Use cyan as a secondary support accent
- Use emerald for safe automation / approval / success
- Keep icon tiles soft and tinted
- Keep spacing generous
- Keep cards rounded and calm
- Make CTAs obvious but not loud

### Don't

- Use too many bright colors on one screen
- Use sharp card corners
- Use heavy shadows everywhere
- Mix icon styles
- Add decorative gradients throughout the product UI
- Use red aggressively unless showing actual risk/error

---

## Tailwind Token Mapping

### Backgrounds

```
bg-slate-50   bg-slate-100  bg-white      bg-slate-950
bg-indigo-50  bg-cyan-50    bg-emerald-50 bg-rose-50  bg-amber-50
```

### Text

```
text-slate-950  text-slate-600  text-slate-500
text-slate-300  text-slate-400
text-indigo-600 text-cyan-600   text-emerald-600
```

### Borders

```
border-slate-200  border-indigo-200  border-emerald-200
```

### Radius

```
rounded-xl  rounded-2xl  rounded-3xl  rounded-full
```

### Shadows

```
shadow-sm  shadow-lg  (custom softer shadows for premium panels)
```

---

## Reusable Component Inventory

Minimum components that should exist in the InboxIQ design kit:

- Primary button
- Secondary button
- Badge / trust chip
- Icon tile
- Standard feature card
- Highlight card
- Success / status card
- Dark emphasis panel
- Section heading block
- KPI / outcome card
- Email thread summary card
- AI action suggestion panel
- Approval policy badge/state
- Calendar availability card
- Audit trail item row

---

## Product-Specific UI References

### Approval Policy States

| State                  |
|------------------------|
| Requires review        |
| Approved for auto-send |
| Sent under policy      |
| Audited                |

### Scheduling Assist Card

| State                          |
|-------------------------------|
| Meeting intent detected        |
| Available slots pulled         |
| Draft reply generated          |
| Waiting for recipient selection |

### Audit Item

| Field       |
|-------------|
| Action taken |
| Policy used  |
| Timestamp    |
| Outcome/result |
| User/AI source |

---

## Implementation Recommendation

Build the design kit in this order:

1. Color tokens
2. Typography tokens
3. Spacing / radius / shadow tokens
4. Reusable card / button / icon components
5. Product-specific panels (approval, scheduling, audit)

Then apply consistently across:

- Homepage
- Dashboard
- Inbox / thread views
- Approval panels
- Scheduling flows
- Audit screens

### Suggested Next Step

Create a dedicated internal page at `/design-kit` containing:

- Colors
- Typography
- Buttons
- Badges
- Cards
- Icon tiles
- Section examples
- Approval policy components
- Scheduling components
- Audit components
