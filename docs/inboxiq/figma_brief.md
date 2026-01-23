# InboxIQ Figma Brief (pre-implementation)

Goal: produce a single-page MVP flow in Figma that matches the slim v1 scope. This brief defines frames, components, and content so we can hand off to build without ambiguity. Keep typography, spacing, and color tokens consistent, and reuse components across frames.

## Frames to create
- Landing (desktop + mobile): hero with value prop, primary CTA, proof points, feature strip, pricing teaser, simple footer.
- OAuth connect screen: choose Gmail/Outlook, show trust badges, one primary button per provider.
- Post-OAuth progress: “Triaging your last 20 emails…” with progress indicator and success banner once 5 tickets are created.
- Ticket queue: table/list with subject, category, priority pill (P0–P2), sentiment chip, link to email, status. Inline override affordance.
- Empty/demo state: seeded sample tickets with demo banner for users without inbox connected.

## Components
- Buttons: primary, secondary, ghost (states: default, hover, pressed, disabled).
- Inputs: text, select, inline dropdown for category/priority override.
- Pills/Chips: priority (P0–P2 color-coded), sentiment (positive/neutral/negative), status (New/Needs review).
- Modals/toasts: small success toast; confirmation modal for overrides.
- Progress indicator: horizontal bar or stepper for triage progress.
- Cards: integration card (Gmail/Outlook) and metric highlight.

## Content & copy (use these strings)
- Value prop: “For small support teams, we solve overwhelming inbox chaos by automatically triaging emails into structured, prioritized tickets — so nothing is missed and response time drops by 80%.”
- CTA: “Connect your inbox” (primary), “View demo” (secondary).
- Feature bullets: Auto-triage → ticket; Priority & sentiment tagging; Entity extraction (order/customer IDs); Works with Gmail & Outlook.
- Progress state: “Triaging your last 20 emails…”, banner: “5 tickets created — go to your queue.”
- Empty/demo banner: “You’re viewing sample tickets. Connect your inbox to see live triage.”
- Override label: “Adjust category/priority.”

## Layout guidance
- Hero: left text, right visual (illustration or abstract inbox-to-ticket flow). Keep CTA above the fold; add trust badges/logos row.
- Ticket queue: responsive table on desktop; stacked cards on mobile. Include search/filter placeholders but non-functional for v1 build.
- Color direction: choose a clear palette (no default blues). Example: deep teal primary, amber for P0, green/gray for sentiment states, neutral grays for surfaces.
- Type: use one purposeful sans (e.g., Sora/Manrope). Set consistent scale (e.g., 32/24/18/16/14) and 4/8px spacing grid.

## Tokens (suggested)
- Colors: `primary #0F766E`, `primary-hover #0B5E57`, `bg #0B1115`, `panel #0F1720`, `border #1F2933`, `text #E5E7EB`, `muted #9CA3AF`, `success #22C55E`, `warning #F59E0B`, `danger #EF4444`, `info #60A5FA`, `priority-p0 #F97316` (amber), `priority-p1 #FACC15` (yellow), `priority-p2 #10B981` (green), `sentiment-neg #EF4444`, `sentiment-neutral #6B7280`, `sentiment-pos #22C55E`.
- Spacing: `4, 8, 12, 16, 24, 32, 40, 56` px increments; base radius `8` (pills `999`), shadows low/med/high.
- Typography: Heading scale `32/24/18/16/14`, line-height 1.3–1.5; font example Sora/Manrope; weights 600/500/400.
- Table/card: row height `56`, cell padding `12–16` horizontal, `10–12` vertical; card padding `16–20`.

## Deliverables
- Published Figma file named “InboxIQ MVP” with pages: `Landing`, `Onboarding`, `Queue`.
- Components in a simple library section with variants for states.
- Export notes for engineering: spacing tokens, colors (# hex), font sizes, icon set if used.

## Hand-off checklist
- Provide frame annotations for padding/margins and breakpoint behavior.
- Mark primary CTA interactions (CTA → OAuth frame → progress → queue).
- Include at least one mobile frame per page.
