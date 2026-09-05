# Design notes — Farebi reviewer console

Why the palette looks the way it does, and why the verdict colours are handled
the way they are. Everything here is enforced in `src/styles/tokens.css`; no
component contains a literal colour.

---

## 1. The brief

A KYC reviewer looks at this screen for hours. The visual job is to be calm
enough to read all day and precise enough to be trusted — *forensic lab meets
stationery*. That translates to:

- **Warm paper, not white.** `--bg: #F2EFE7` and `--surface: #FAF8F3`. Pure
  `#FFF` at full-screen scale is fatiguing and makes every pastel look dirty.
- **Ink, not black.** `--text: #1D2A3A` (Deep Slate). Pure `#000` on a warm
  background reads as a printing error.
- **Flat, bordered surfaces.** 12px radius, 1px `--border` (Slate Fog), and a
  single shadow token capped at `0 1px 2px rgba(29,42,58,.06)`. Elevation is
  not information here; every card has the same standing.
- **Mono for anything a reviewer might quote.** Probabilities, strengths,
  signal codes, request IDs, version strings, quality readouts. If it could end
  up pasted into an escalation ticket, it is JetBrains Mono.

---

## 2. Token roles

### Foundations

| Token | Value | Role |
| --- | --- | --- |
| `--bg` | `#F2EFE7` Warm Linen | Page background |
| `--surface` | `#FAF8F3` Paper | Cards, popovers, the "on" tab |
| `--surface-sunken` | `#EAE5D9` Oat | Dropzone, tablist trough, inset panels, progress tracks |
| `--border` | `#DCE4E8` Slate Fog | Default 1px hairline |
| `--border-strong` | `#C4CFD6` Pewter | Secondary buttons, dashed dropzone, form controls |
| `--text` | `#1D2A3A` Deep Slate | Body and headings |
| `--text-2` | `#3E4E5E` Harbor | Secondary prose, labels |
| `--text-3` | `#5A6775` Driftwood | Limitations and disclaimers |
| `--focus` | `#3368A0` | Focus ring, everywhere, always visible |

### Hues

| Ramp | Anchor | Role |
| --- | --- | --- |
| `--blue-*` | `#3368A0` | Primary. Buttons, links, focus, `toward_real` evidence. |
| `--sky-*` | `#66A3BF` | Secondary. Cool end of the attribution ramp, quiet fills. |
| `--aqua-*` | `#C8DFDB` | Tertiary. Illustration and decorative surfaces only. |
| `--terracotta-*` | `#D97757` | Warm primary accent. `toward_fake`, errors, critical quality. |
| `--ochre-*` | `#E0AD6B` | Warm secondary accent. Warnings, uncertainty, the amber band zone. |
| `--sage-*` | `#88A795` | Earth tone. Quality pass, the green band zone. |

Three warm accents against a cool blue primary is what stops the UI reading as
a generic dashboard. Terracotta and ochre are also genuinely easier to separate
from blue for the most common colour-vision deficiencies than a red/green pair
would be — which matters, because "toward fake" and "toward real" appear side
by side in every signal row.

### Ink darkening

`--text-2`, `--text-3`, `--ochre-700`, `--terracotta-700` and `--sage-700` were
each darkened from their first draft until they cleared 4.5:1 against the
*darkest* surface they are ever painted on (`--surface-sunken`, `--ochre-100`,
`--terracotta-100`, `--sage-100` respectively). `npm run check:contrast` parses
`tokens.css` and re-proves all 24 pairs on demand, so this cannot silently rot.

One consequence worth naming: the `--text` → `--text-2` → `--text-3` ramp is
more compressed than a typical design system's, because the bottom of the ramp
is pinned by the contrast floor rather than by taste. Hierarchy is therefore
carried mostly by **size and weight** (15px body / 13px note / 12px micro), not
by lightness alone. That is the better practice anyway.

---

## 3. Verdict colours: anchors vs. fills

`frebi.md` §1.1 mandates four exact hues:

| Verdict | Mandated |
| --- | --- |
| `likely_real` | `#22c55e` |
| `likely_fake` | `#ef4444` |
| `uncertain` | `#eab308` |
| `unable_to_assess` | `#6b7280` |

These are saturated utility-CSS defaults. Used as large background washes they
fight the pastel foundation, and used as text they fail contrast: `#eab308` on
white is 1.9:1, and `#22c55e` is 1.9:1 — nowhere near the 4.5:1 that §10
requires in the very same document.

So each verdict gets **four** tokens rather than one:

| Token | Use | Why |
| --- | --- | --- |
| `--v-*-anchor` | 4px card stripe, legend dots, probability-bar fill, band-zone key swatches | The mandated hue, rendered at a size where saturation is an asset. The §1.1 contract is visibly and literally met. |
| `--v-*-fill` | Verdict card background | Desaturated toward the paper foundation so the card sits in the palette. |
| `--v-*-ink` | Verdict card text | Darkened until ≥ 4.5:1 on its own fill. |
| `--v-*-border` | Verdict card border | Drawn from the warm accent ramps, tying the verdict back to the rest of the UI. |

Measured results: Likely Real 5.13:1, Likely Fake 5.62:1, Uncertain 5.24:1,
Unable to Assess 7.26:1.

The anchor hue is never the only carrier of the verdict. Each card also shows a
glyph (`✓ ✕ ? –`) and the mandated label text, so the state survives greyscale
printing, colour-blind viewing, and a screen reader.

---

## 4. Semantic colour rules

| Meaning | Colour | Redundant cue |
| --- | --- | --- |
| `toward_fake` | `--terracotta-500` | `↑` + the words "toward fake" |
| `toward_real` | `--blue-500` | `↓` + the words "toward real" |
| `toward_uncertain` | `--ochre-500` | `→` + the words "toward uncertain" |
| `neutral` | `--text-3` / `--border-strong` | `→` + the word "neutral" |
| Quality pass | `--sage-500` | `✓` + "All checks passed" |
| Quality warn | `--ochre-500` | `!` + "Warnings" |
| Quality fail | `--terracotta-500` | `✕` + "Critical" |
| Warning surface | `--ochre-50` bg, `--ochre-700` ink, `--ochre-500` border | `⚠` + a screen-reader-only "Warning:" prefix |
| Error surface | `--terracotta-50` bg, `--terracotta-700` ink | `✕` + a named error kind |

### Attribution ramp

The heatmap legend runs
`--blue-500 → --sky-500 → --bg → --ochre-500 → --terracotta-500 → --terracotta-700`,
i.e. *toward real* → neutral → *toward fake*. It reuses the same two hues that
mark signal direction everywhere else, so the map and the signal list teach
each other. The neutral midpoint is the page background rather than white,
which is what lets the overlay blend cleanly with `mix-blend-mode: multiply`.

### Band indicator

Zones use the `-100` tints (`--sage-100`, `--ochre-100`, `--terracotta-100`)
rather than the anchors, because the marker and the tick labels have to stay
legible *on top of* them. The `p_fake` marker is `--text` — the darkest thing
on screen — because its exact position is the point of the component.

---

## 5. Typography and motion

- Inter for UI, JetBrains Mono for anything quotable. 15px base, 1.55 line
  height, 13px notes, 12px micro.
- Motion is one token: `--motion: 170ms` with an ease-out curve, applied to
  colour and width transitions only. Nothing slides, nothing bounces.
- `prefers-reduced-motion` sets `--motion: 0ms` and a global override kills
  every remaining transition and animation.

---

## 6. Things the palette deliberately does not do

- **No dark mode.** Two colour schemes means two contrast audits and two sets
  of verdict fills. A forensic judgement should not shift with an OS toggle,
  and the risk of shipping an unaudited second theme outweighs the comfort.
- **No shadow-based hierarchy.** Every card is equally authoritative. Making
  the verdict "float" would imply the signals below it matter less, which is
  exactly the wrong message for a tool whose whole thesis is that a single
  number should never be acted on alone.
- **No colour-only affordances.** Checked mechanically by the render smoke
  test, which strips all markup and asserts the state words are still there.
