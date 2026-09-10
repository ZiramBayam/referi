---
name: Referi
description: A proof gate for autonomous value movement, an instrument panel, not an activity dashboard.
colors:
  bg: "oklch(0.145 0 0)"
  surface: "oklch(0.185 0 0)"
  surface-2: "oklch(0.225 0 0)"
  border: "oklch(0.275 0 0)"
  border-strong: "oklch(0.34 0 0)"
  ink: "oklch(0.975 0 0)"
  muted: "oklch(0.74 0 0)"
  faint: "oklch(0.58 0 0)"
  primary: "oklch(0.522 0.267 263.3)"
  primary-hover: "oklch(0.575 0.247 263)"
  primary-ink: "oklch(0.78 0.13 263)"
  on-primary: "oklch(0.99 0 0)"
  ring: "oklch(0.7 0.2 263)"
  proof-pass: "oklch(0.72 0.17 152)"
  proof-review: "oklch(0.8 0.15 85)"
  proof-block: "oklch(0.62 0.21 25)"
typography:
  display:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "clamp(2.4rem, 6vw, 4.25rem)"
    fontWeight: 600
    lineHeight: 1.04
    letterSpacing: "-0.03em"
    fontVariation: "opsz, SOFT, WONK"
  headline:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "clamp(1.8rem, 3.5vw, 2.6rem)"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Hanken Grotesk, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.625
    letterSpacing: "normal"
  body-compact:
    fontFamily: "Hanken Grotesk, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.625
    letterSpacing: "normal"
  label:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.025em"
  data:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.625
    letterSpacing: "normal"
rounded:
  ring: "6px"
  chip: "8px"
  control: "10px"
  panel: "12px"
  card: "14px"
  evidence: "16px"
  console: "20px"
  pill: "9999px"
spacing:
  gutter: "20px"
  hairline-row: "12px"
  control-pad: "16px"
  card-pad: "20px"
  console-pad: "24px"
  block: "32px"
  column-gap: "48px"
  section: "64px"
  section-tall: "80px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-primary-lg:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.control}"
    padding: "0 24px"
    height: "48px"
  button-secondary:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
  gate-console:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.console}"
    padding: "0"
  input-amount:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    typography: "{typography.data}"
    rounded: "{rounded.panel}"
    padding: "0 16px"
    height: "56px"
    width: "384px"
  tag-pass:
    textColor: "{colors.proof-pass}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 8px"
  tag-review:
    textColor: "{colors.proof-review}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 8px"
  tag-block:
    textColor: "{colors.proof-block}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 8px"
  nav-link:
    textColor: "{colors.muted}"
    typography: "{typography.body-compact}"
    rounded: "{rounded.chip}"
    padding: "6px 12px"
  nav-link-active:
    textColor: "{colors.primary-ink}"
    typography: "{typography.body-compact}"
    rounded: "{rounded.chip}"
    padding: "6px 12px"
---

# Design System: Referi

## Overview

**Creative North Star: "The Instrument Panel"**

Referi looks like an instrument, not a report. The product's whole claim is that a
past incident becomes a *precondition*, something that stands between an agent and
a transaction, so the interface has to look like a thing that can refuse, not a
thing that narrates. Every surface is a quiet chroma-0 ground with hairline-bordered
panels laid on it, and the only saturated marks on the page are the ones that carry a
decision: one brand blue for control, three signal colors for proof state. Nothing is
tinted for mood.

The system is a port of the Veritas-UHI9 instrument world, pinned by the client as the
visual authority (PRODUCT.md, "Brand Commitments"), with Referi supplying every fact.
It is genuinely dual-theme: `oklch(0.145 0 0)` dark and `oklch(0.995 0 0)` light,
both chroma-0, never a tinted near-black and never an off-white that leans warm. Type
is a three-family pairing that separates the kinds of statement being made, Fraunces
for the display voice, Hanken Grotesk for prose, IBM Plex Mono for anything that is a
fact you could check.

Density is high but never crowded: an 1152px container, 20px gutters, and hairline
rules that let a reader scan a panel row by row. Depth is done with one surface step
and a 1px border; there is exactly one `box-shadow` utility in the entire codebase and
it is a 1px inset highlight on the primary button. Motion is rationed to a single
authored moment, the gate resolving, and everything else is feedback.

**Key Characteristics:**

- Chroma-0 neutral scale in oklch; every hue on screen is doing decision work
- One brand blue (`#004eff`) for control, three proof colors for obligation state
- 14px hairline-bordered panels on a quiet surface; no shadow vocabulary
- Fraunces display / Hanken Grotesk prose / IBM Plex Mono data
- True light and dark, chosen before first paint, toggled by a real control
- One authored motion moment; state swaps are enter-only and never animate a number

## Colors

A chroma-0 neutral scale carrying all structure, with saturation reserved entirely
for control and proof state. Both themes are defined at full strength in
`web/src/app/globals.css`; the light theme is not a filter over the dark one.

### Primary

- **Referi Blue** (`--primary`): the single brand and control color. It fills the
  primary button, the Referi mark, the active stage underline, and the solid cells of
  the ProofLens field. It never appears as a decorative wash.
- **Blue Hover** (`--primary-hover`): the primary button's hover fill. Lighter in
  dark, darker in light, the direction of the shift reverses with the theme.
- **Readable Blue** (`--primary-ink`): the *text* blue. Referi Blue at full strength
  is unreadable as small type on either ground, so every blue word, icon, inline link,
  and hairline accent uses this token instead, nav labels on their active pill, the
  action class in the gate console, external-link chevrons, scanline gradient.
- **Ring Blue** (`--ring`): focus indication only. It is never a fill.
- **On-Primary** (`--on-primary`): the near-white that sits on a Referi Blue fill.

### Secondary

There is none, and that is a decision. A second accent would compete with the proof
colors for the reader's attention, and the proof colors are the ones that mean
something.

### Tertiary, the proof signals

Three hues, reserved for one axis only: the status of a proof obligation. They are
never used for emphasis, illustration, or category.

- **Proof Pass** (`--proof-pass`, green): an obligation is satisfied; a passport was
  issued; a stage is complete; the verifier accepted the one call it was going to
  accept.
- **Proof Review** (`--proof-review`, amber): a fact could not be verified, so a human
  is required. Amber is also the color of the *seeded incident* panel and the fixture
  status dot in the nav, the shared meaning is "known-uncertain", never "warning as
  decoration" and never "nearly passed".
- **Proof Block** (`--proof-block`, red): an obligation failed and the action is held.
  It also carries input validation errors and the refused-replay rows.

Signal colors always appear at low alpha as fill (`/10`–`/12`) with a mid-alpha border
(`/40`–`/60`) and the token itself as the text color. A signal is never a solid block.

### Neutral

- **Ground** (`--bg`): the page. Also the inner ground of a panel nested inside a
  panel, which is how a row inside the gate console reads as recessed rather than
  raised.
- **Surface** (`--surface`): one step up from the ground. Cards, the gate console,
  evidence panels, the sticky nav at 75% with a backdrop blur.
- **Surface Raised** (`--surface-2`): two steps up. Secondary buttons and the
  "awaiting" decision chip, the only places a control needs to read as sitting on top
  of a card.
- **Hairline** (`--border`): the default border for everything, and the global
  `border-color` for all elements. This is the workhorse of the whole system.
- **Hairline Strong** (`--border-strong`): the border that answers a hover, the
  scrollbar thumb, and the structural strokes inside the GateChain illustration.
- **Ink** (`--ink`): primary text and any value that is the answer to a question.
- **Muted** (`--muted`): prose, descriptions, secondary rows. The reading color.
- **Faint** (`--faint`): the small mono labels, obligation ids, file paths, table
  keys, unit suffixes, "not available".

### Named Rules

**The Signal Rarity Rule.** Blue is the only brand and control color; `--proof-pass`,
`--proof-review`, and `--proof-block` exist to say what a proof obligation did, and
nothing else. If a color is on the screen and you cannot name the decision it reports,
remove it. Test: on any full page, the saturated pixels should all be traceable to a
control the user can press or a state the verifier produced.

**The Never-Color-Alone Rule.** No status is ever carried by color alone. Every proof
state ships an icon *and* a word: `PASS` with a check, `BLOCK` with an X, `REVIEW`
with a triangle (`PROOF_TONE` and `DECISION_TONE` in
`web/src/components/ExecutionRoom.jsx`; `Tag` in `web/src/components/PageShell.jsx`).
A new state needs all three or it does not ship.

**The Legibility-Over-Parity Rule.** Where the reference world and legibility
disagree, legibility wins and the deviation gets written down. Light-theme `--faint`
is `oklch(0.47 0 0)`, not the reference's `0.56`: at `0.56` it measures roughly 3.7:1
on the light ground, below WCAG AA 4.5:1, and this token carries the small mono labels
that name obligations and files. The visual difference is imperceptible; the contrast
failure was not. Recorded in `docs/decisions.md` ADR-032 §6.

**The Two Real Themes Rule.** Light is not a computed inversion. Both themes declare
every token, and three of them change meaning between themes rather than just value:
`--primary-hover` reverses direction, `--primary-ink` darkens to clear 7:1 on white,
and all three proof hues darken so colored text stays readable on a light tint.

## Typography

**Display Font:** Fraunces (with Georgia, serif), variable, with the `opsz`, `SOFT`,
and `WONK` axes loaded
**Body Font:** Hanken Grotesk (with system-ui, sans-serif)
**Label/Mono Font:** IBM Plex Mono (with ui-monospace, monospace), weights 400/500/600

**Character:** A soft, slightly wonky serif over a neutral humanist grotesque over a
severe engineering mono. The pairing is doing semantic work, not decorative work: the
serif makes claims, the grotesque explains them, and the mono is reserved for things a
reader could go and check. All three are OFL-licensed and self-hosted at build time by
`next/font/google` (`web/src/fonts/veritas-fonts.js`, provenance in
`web/src/fonts/NOTICE.md`); the running site fetches no font from a third party.

### Hierarchy

- **Display** (600, `clamp(2.4rem, 6vw, 4.25rem)`, 1.04, -0.03em): the single page
  headline on the overview. One per page, and it states the thesis as a sentence
  ("An agent should not repeat the failure it already survived.").
- **Headline** (600, `clamp(1.6rem–1.8rem` → `2.2rem–2.6rem)`, 1.25): section
  headlines, the passport, the refusal, the outcome, the memory argument. Every
  headline in the build is a complete sentence with a full stop.
- **Title** (600, 20px / 18px in the console header, 1.4): panel and card headings.
  Inner-page titles use 36px (`PageHeader`), the same role at page scale.
- **Body** (400, 15px, 1.625): prose and ledes, capped at `max-w-xl`/`max-w-2xl`
  (roughly 60–70ch). A 14px step handles denser panel prose and a 13px step handles
  in-panel explanations; 18px is used once, for the hero sub-paragraph.
- **Label** (500/600, 11px, 0.025em, uppercase): proof-state words, decision chips,
  status tags, group labels. Always mono.
- **Data** (400, 12px, 1.625): obligation ids, hashes, addresses, file paths, chain
  labels, JSON. Mono, and often at `--faint` when it is a key rather than a value.

Global base rules: `h1`–`h3` get Fraunces, `text-wrap: balance`, and `-0.02em`
tracking automatically; paragraphs get `text-wrap: pretty`.

### Named Rules

**The Mono-Carries-Fact Rule.** IBM Plex Mono marks a checkable fact: an id, a hash, a
calldata shape, a threshold, an amount, a state word. Prose never uses it, and a
number that is a claim about state is never set in the prose face.

**The Tabular Number Rule.** Any figure that can change under the reader, a reserve,
an amount, a count, carries `.tnum` (`font-variant-numeric: tabular-nums`) so digits
do not reflow between states.

**The Sentence Headline Rule.** Headlines are sentences with full stops, not labels.
"The passport is the gate." and "Exact action executed." are the house voice; "Gate
Console" is not.

## Layout

One container everywhere: `max-w-6xl` (1152px) centered, with 20px side gutters
(`px-5`) held at every breakpoint. `Page` in `web/src/components/PageShell.jsx` owns it
for the evidence routes so they cannot drift from the execution room, which declares
the same pair inline on each of its sections.

Two surfaces, deliberately split. The overview (`/`) is a reading surface: a
`lg:grid-cols-[1.05fr_0.95fr]` hero pairing the thesis with a summary of what is
enforced, then long-form sections. It holds no live gate, so it can be read without
being operated first, and its single primary action leads into the execution room.

The execution room (`/execution`) is the signature composition, and it is sequential
rather than side by side: a sticky stage rail under the nav, then four numbered
`<section>` steps in the order the agent actually runs them, propose, preflight,
passport, execute. Each step declares its own state in its number disc, and a step
that cannot be reached yet is not rendered at all, because an empty dimmed step still
reads as something pressable. Inside step 02 the split returns at
`lg:grid-cols-[1.15fr_0.85fr]`: obligations on the left because that is where the
reason is read, the decision and its action on the right, `lg:sticky lg:top-40`.

Downstream sections use deliberately uneven two-column splits, `0.85fr/1.15fr` for
the passport and outcome (argument left, artifact right), `0.9fr/1.1fr` for the memory
argument, `0.95fr/1.05fr` for the reproduction band. The footer is
`sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr]`.

Vertical rhythm: 64px section padding (80px for the two long-form sections, 56px for
inner pages), 24px for the stage rail, 48px footer block. Sections are separated by a
single `border-b` hairline, never by whitespace alone. The nav is 64px tall and
sticky; the mobile section nav is a second 40px row that scrolls horizontally, because
below `md` the primary links would otherwise only be reachable from the footer.

Grid-of-cells patterns (the stage rail, the three-step memory explainer) are built as
`gap-px` grids on a `bg-border` parent with `bg-bg` children, the gap *is* the
hairline, so cells share a 1px rule instead of stacking two borders.

### Named Rules

**The One Container Rule.** 1152px and 20px gutters, on every route, at every width.
A surface that needs more room gets a wider internal grid, not a wider container.

**The Hairline Separates Rule.** Structure is communicated by 1px rules, not by
padding. If two blocks need to read as distinct, put a border between them.

## Elevation & Depth

This system has no shadow vocabulary. Depth is entirely tonal plus hairline: a surface
moves up by one step on the neutral ramp (`--bg` → `--surface` → `--surface-2`) and
gets a 1px `--border`. Nesting inverts, a panel inside the gate console drops *back*
to `--bg`/`--bg-at-60%`, so recession reads as clearly as elevation.

There is exactly one `box-shadow` utility in the codebase: a 1px inset white highlight
on the primary button (`shadow-[0_1px_0_oklch(1_0_0/0.12)_inset]`), which gives the
page's only saturated fill a physical top edge. There is no ambient shadow, no card
lift, and no hover elevation anywhere.

Two non-shadow depth devices carry the rest of the work: the sticky nav uses
`bg-bg/75` with `backdrop-blur-xl` so content passing under it stays legible without a
drop shadow, and the ProofLens canvas sits at `z-0` behind a `z-10` stacking context,
an atmospheric layer, not a lit one.

### Named Rules

**The Flat-Forever Rule.** No shadows. A surface that needs to stand out changes its
tone step or its border, never its elevation. The one inset highlight on the primary
button is a material edge, not a shadow, and it is not a pattern to extend.

**The Recess-By-Nesting Rule.** Inside a raised panel, sub-panels go back down to the
page ground. Two consecutive raises never stack.

## Shapes

Radius is a ladder tied to the size and consequence of the container, not a single
value applied everywhere:

- **6px**, the global `:focus-visible` ring's own corner
- **8px** (`rounded-lg`), nav pills, status tags, decision chips, the theme toggle
- **10px**, buttons, all three variants and all three sizes
- **12px** (`rounded-xl`), panels inside panels: the proposed-action block, the
  fixture controls, the notice band, the stage rail
- **14px** (`--radius` / `rounded-card`), the `Card` primitive, the system's default
  panel corner
- **16px** (`rounded-2xl`), evidence cards, tables, figures, the reproduction manifest
- **20px**, the three signature surfaces only: the gate console, the passport, and
  the outcome test list
- **full**, status dots, obligation state discs, the ping ring, disclosure pills

Borders are always 1px and always `--border` unless the element is reporting state, in
which case the border becomes that state's token at 30–60% alpha. Strokes inside the
one illustration use `--border-strong` for structure and `--ink` at 2.5px for the gate
bars themselves.

The recurring geometry is a **ring around an angled stamp**: four arc segments (one per
proof obligation) enclosing a 45°-rotated square. It is the Referi mark
(`web/src/components/Logo.jsx`) and the same stamp reappears as the passport glyph in
the GateChain illustration, so the mark and the mechanism are visibly the same object.
The circle-versus-angle contrast is deliberate, it keeps the mark from ever reading as
a loading spinner.

### Named Rules

**The Radius Ladder Rule.** Corner radius rises with the weight of the container:
8px for chips, 10px for controls, 12–14px for panels, 16px for evidence, 20px for the
three surfaces that carry the product's central claim. Do not give a new element 20px
unless it is a peer of the gate console.

## Components

### Buttons

Compact, square-shouldered, and quiet. Three variants, three sizes, defined once in
`web/src/components/ui/Button.jsx` and consumed as a class string (`buttonClasses`) so
that `<a>` and `<button>` render identically.

- **Shape:** 10px radius at every size, flatter than the panels they sit on.
- **Sizes:** sm 32px tall / 12px padding / 13px text; md 40px / 16px / 14px;
  lg 48px / 24px / 15px.
- **Primary:** Referi Blue fill, near-white text, 1px inset highlight. Hover moves to
  `--primary-hover`; every variant drops 1px on `:active`.
- **Secondary:** `--surface-2` fill with a hairline that strengthens on hover. This is
  the workhorse, every fixture control, every "try it" test, every in-page jump.
- **Ghost:** muted text that gains ink and a `--surface` wash on hover.
- **Focus:** the primary variant carries its own 2px `--ring` **outline** at 2px
  offset; the other variants use the global `:focus-visible` double box-shadow ring.
  Both read identically.
- **Disabled:** 50% opacity, pointer events off. A disabled primary that has finished
  its job changes *variant* rather than just dimming, the executed passport button
  becomes a secondary with a green check, because a dimmed blue button still reads as
  an invitation.

**The Focus Ring Survives Rule.** Never add `focus-visible:outline-none` to the Button
base string. The base layer already removes the browser outline for the whole page and
replaces it with a box-shadow ring; the primary variant's inset-highlight `shadow-*`
utility overrides that ring, which is why it declares an `outline` of its own. Re-add
the utility and the page's main action becomes the only control invisible under Tab.

### Cards / Containers

- **Corner:** 14px (`--radius-card`) for the `Card` primitive; 16px for evidence
  cards; 20px for the gate console, passport and outcome list.
- **Background:** `--surface`, or `--surface/30`–`/40` for bands that should read as a
  tint of the section rather than a panel.
- **Shadow strategy:** none, see Elevation & Depth.
- **Border:** 1px `--border`, or a proof token at 25–40% when the card reports state.
- **Internal padding:** 20px×16px for evidence cards, 24px×16–20px for the gate
  console, 28px for the three-step explainer cells, 16px for control rows.
- **Header pattern:** cards that carry a title use a `border-b` header strip with the
  title left and a mono tag or status right, then an unpadded body.

### Inputs / Fields

One real input in the build: the rebalance amount.

- **Style:** 56px tall, 12px radius, page-ground fill (not surface), hairline border,
  20px mono value at `.tnum`, and a `--faint` mono unit suffix pinned to the right.
- **Focus:** `focus-within:border-primary` on the wrapper, the field is a single
  object, so the whole frame responds, not the bare `<input>`. Caret color is
  `--primary-ink` globally.
- **Error:** the border becomes `--proof-block`, `aria-invalid` is set, and a 12px
  block-colored sentence states the accepted range. The word does the work; the color
  agrees with it.

### Navigation

Sticky 64px header on `bg-bg/75` with `backdrop-blur-xl` and a bottom hairline. Links
are 14px medium pills; the active one takes a `--primary/20` fill with `--primary-ink`
text plus a 2px `--primary-ink` underline that **slides** between links via a shared
`layoutId`, one marker moving, not four appearing. Under `prefers-reduced-motion` the
marker renders as a static span.

Right side: a mono chain badge with an amber pulsing dot and the word `fixture`, then
the theme toggle (36px square, hairline, sun/moon). Below `md` the link row moves to a
second horizontally scrollable strip under the header.

Footer: three columns over the same container, product links, an evidence column whose
external links carry a 12px chevron that turns `--primary-ink` on hover, and a bottom
hairline bar holding the fixture disclosure in mono.

### Status Tag

`Tag` (`web/src/components/PageShell.jsx`) is the portable state marker: 8px radius,
11px uppercase mono, icon + word, with the state token at 10% fill / 40% border / full
text. `pass` is green with a check, `fail` is red with an X, and **anything else** is
amber with a triangle, an unrecognised status is treated as unverified, never as a
silent pass.

### Key/Value List

`KeyValues` / `KeyValue` render a `<dl>` as a two-column grid
(`minmax(0,14rem)_1fr`) at `sm+` and stacked below it. Each row is separated by a
`border-t` hairline, the key is 12px `--faint` mono, the value is 14px `--ink` with
`break-words`. This is the default shape for any evidence payload, and it is the
reason the verdict, timeline, panel and firewall routes look like one product.

### Notice

A context band, 12px radius, icon left. `info` is a plain `--surface` panel with a
`--primary-ink` info glyph; `warn` is a `--proof-review/[0.06]` tint with a triangle
and an amber hairline. An optional bold `title` runs inline with the body text rather
than sitting on its own line.

### Execution Gate Console (signature)

The product's central surface: a 20px-radius `--surface` panel with three stacked
regions, a header carrying the title and a live decision chip, a recessed
proposed-action block on the page ground, and the obligation list. It is `aria-live="polite"`
and sticky at `lg`.

The **one authored motion moment** lives here:

1. **Scanline.** While preflight runs, a `--primary-ink` gradient line sweeps the
   placeholder panel (`.scanline`, 1.15s, `--ease-out-quart`) and stops when the run
   does. The sweep distance is passed in as `--scan-distance`.
2. **Staggered arrival.** Obligation rows enter from `x: 10` at 75ms intervals,
   420ms, `ease-out-expo`. The list is keyed by run index, so re-running the same
   preflight replays the stagger instead of silently swapping values.
3. **Key-first decision chip.** The chip is replaced whole on every decision change,
   enter-only, 240ms, no exit.
4. **The passport unseals.** `clip-path: inset(0 0 100% 0)` → `inset(0 0 0% 0)` over
   750ms: a seal breaking downward, not a card fading in.

Obligation rows are `<details>` elements that are **open by default when they did not
pass**, a refusal never hides its reason, each showing the proof label, its mono id,
the state word, an explanation, and an Observed/Required pair.

**The No-Exit Rule.** `AnimatePresence` is not used anywhere in this project, and no
state element has an exit animation. A stale passport or decision chip that fades out
still reads as *permission* for as long as it is on screen. Invalidated results
disappear instantly; state swaps are keyed and enter-only
(`docs/decisions.md` ADR-032 §4).

**The Numbers Never Animate Rule.** The reference kit's `CountUp` is deliberately not
adopted. It sat on the post-action treasury reserve, which is a factual claim about
state, and a `requestAnimationFrame` throttled in a background tab leaves a wrong
figure on screen. State values render as-is (ADR-032 §5).

### Stage Rail

A four-cell `<ol>` pinned under the nav at the top of the execution room, so the
visitor's position in the flow stays legible however far they scroll: `gap-px` on
`bg-border` so the cells share hairlines, each with a numbered 24px disc and a label. Completed stages
take `--proof-pass` and swap the number for a check; the active stage takes
`--primary` and gets a 2px underline that slides between cells via `layoutId`, the
same grammar as the nav marker.

### ProofLens (ambient canvas)

A full-viewport `z-0` canvas mounted only on `/`. A static field of neutral chroma-0
dots (unproven claims) hardens into a blue grid of solid squares, outlined squares and
faint dots (satisfied, bound-but-unproven, non-binding) inside a lens that follows the
pointer, then decays at a fixed rate so the hardened patch trails the cursor and fades
in about 0.8s. Intensity is driven by the theme-aware `--wave-alpha` token (0.5 dark /
0.7 light).

**The Activity-Gated Canvas Rule.** The `requestAnimationFrame` loop *stops* once the
lens settles and the reveal has decayed, an idle page paints nothing. It also stops on
`visibilitychange`. Under `prefers-reduced-motion` it renders one static resolved frame
and never tracks the pointer.

### GateChain (the one illustration)

The only illustration in the product, and it exists because prose cannot show the
shape of the mechanism: one incident → one hypothesis → four obligations converging on
a single gate → one single-use passport → exactly one accepted exit and one refused
replay. All strokes and fills are token-driven, so it changes with the theme, and it
carries `role="img"` with a linked `<title>`/`<desc>`.

**The Draw-It-Twice Rule.** The diagram is authored twice, a horizontal composition
at `sm+` and a genuinely re-derived stacked one below `sm`, not scaled. A horizontal
SVG squeezed to 340px puts its labels near 7px, and an unreadable diagram is worse
than no diagram. The stacked version re-solves the convergence too: the four
obligations gather onto a single rail before touching the gate, because the gate is
below rather than beside them.

## Do's and Don'ts

### Do:

- **Do** take every color from `web/src/app/globals.css`. The `:root` /
  `[data-theme="light"]` pair is the only source of truth, and `@theme inline`
  re-exports them as Tailwind utilities.
- **Do** ship an icon and a word with every state, in every new component
  (The Never-Color-Alone Rule).
- **Do** hold the container at `max-w-6xl` with `px-5`, and reach for
  `PageShell`'s `Page` on any new evidence route.
- **Do** build depth with a tone step plus a hairline; use `gap-px` on a `bg-border`
  parent when cells should share one rule.
- **Do** set every checkable fact, ids, hashes, thresholds, amounts, paths, in IBM
  Plex Mono, and add `.tnum` to any figure that changes.
- **Do** key state swaps and animate them on enter only.
- **Do** render an unavailable value as the words "not available"
  (`NotAvailable`), never as a dash and never as a placeholder hash.
- **Do** label the earlier evaluator direction wherever it appears. `/firewall` and
  `/timeline` say so in their own ledes and the footer marks the Escrow Firewall link
  "earlier direction", PRODUCT.md requires that no surface present those pages as the
  current product direction.
- **Do** give a `prefers-reduced-motion` path that renders the *content*, not a hidden
  element: `Reveal` returns a plain tag, `ProofLens` paints one resolved frame, sliding
  markers become static spans.

### Don't:

- **Don't** introduce a second accent color, or use a proof color for anything but
  proof state. Amber is not "attention", green is not "good", red is not "important".
- **Don't** add `focus-visible:outline-none` to the Button base string, or to any
  control whose variant carries a `shadow-*` utility (The Focus Ring Survives Rule).
- **Don't** import `AnimatePresence` or add an exit animation to a result, a chip, a
  passport, or a refusal.
- **Don't** animate a number that describes state.
- **Don't** add a `box-shadow` for elevation. The system is flat; the one inset
  highlight on the primary button is not a precedent.
- **Don't** tint the neutrals. Both grounds are chroma-0; a near-black with a blue cast
  is the thing this world was defined against.
- **Don't** scale a diagram down to fit a phone. Draw the small one.
- **Don't** run a `requestAnimationFrame` loop that does not stop on its own.
- **Don't** define a color, radius or easing in a component. If it is reusable it
  belongs in `globals.css`; if it is not reusable it is not a system value.
- **Don't** stack two raised surfaces. Nest downward to the page ground instead.
