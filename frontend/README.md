# Farebi Frontend

Reviewer console for the Farebi image-manipulation detector. React 18-style
hooks on React 19 + TypeScript + Vite + Tailwind, no UI kit, no router, no
analytics.

It implements [`../frebi.md`](../frebi.md) in full. `frebi.md` is the source of
truth for behaviour and copy; this README documents how to run the thing and
where each requirement lives.

---

## Quick start

```bash
cd frontend
npm install
cp .env.example .env.local     # ships with VITE_MOCK_API=true
npm run dev                    # http://localhost:5173
```

Or from the repo root, `make ui-setup && make ui`.

> **If the app suddenly won't start**, `node_modules/` and `.env.local` are both
> untracked and are not preserved by sandbox/workspace snapshots. Everything
> under `src/` is committed and safe. Restore with `make ui-setup` (or
> `npm ci && cp .env.example .env.local`) and start it again.

With mock mode on you get a scenario picker in the header and the whole UI is
demoable with no backend running.

To point at a real API instead:

```bash
# .env.local
VITE_MOCK_API=false
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000
```

then start the FastAPI app (`make serve` from the repo root) and reload.

### Scripts

| Script | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on `0.0.0.0:5173`, proxying `/v1`, `/health`, `/ready`. |
| `npm run build` | Typecheck, then production build to `dist/`. |
| `npm run preview` | Serve the production build. |
| `npm run typecheck` | `tsc --noEmit`. |
| `npm run check:contrast` | Parses `tokens.css` and fails if any text/background pair is below 4.5:1. |
| `npm run check:render` | SSR-renders every fixture and asserts the mandatory copy is present and no percentages or certainty language leak out. |
| `npm run check` | All three of the above. |

`check:render` is the interesting one: it renders each verdict fixture and each
error fixture, then asserts the §1.2 probability sentence appears verbatim in
both the visible text and the bar's `aria-label`, that every applicable signal
prints its `limitation`, that the heatmap notice, per-result warning and
privacy banner are present, and that nothing anywhere renders a `%` next to a
number or the words "guaranteed" / "detected a deepfake".

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE` | `""` (same origin) | Base URL of the API. Leave empty in dev so the browser calls relative URLs and Vite proxies them — this is what keeps the app working behind a remote preview host. |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the dev server forwards `/v1`. |
| `VITE_MOCK_API` | `true` in `.env.example` | Serve fixtures instead of calling the API. |
| `VITE_REQUEST_TIMEOUT_MS` | `30000` | Client-side abort deadline (§9.2). |
| `VITE_MAX_UPLOAD_BYTES` | `10485760` | Pre-upload size gate (§2.2). |
| `VITE_MAX_PIXEL_DIM` | `2048` | Pre-upload dimension gate (§2.2). |

Client-side validation is a courtesy that gives the reviewer a faster, more
specific rejection. It is **not** a security boundary —
`src/farebi/core/security.py` remains authoritative, and the API re-checks
magic bytes, size, dimensions and frame count on every request.

---

## Mock mode

`VITE_MOCK_API=true` swaps the network call for `src/mocks/fixtures.ts` and
adds a scenario `<select>` to the header:

- **Verdicts** — `likely_real`, `likely_fake`, `uncertain`, `unable_to_assess`
- **Errors** — no face, face too small, corrupt file, multi-frame, HTTP 500, timeout

Each verdict fixture carries realistic signals (`FFT_FREQUENCY`,
`CLIP_CLASSIFIER`, `FACE_GEOMETRY`, `TEXTURE_INCONSISTENCY`,
`MODEL_DISAGREEMENT`, `METADATA_UNAVAILABLE`, plus `EYE_REFLECTION` marked
inapplicable so §3.3 is always exercised), a full `quality` dict, and a tiny
64×64 base64 PNG attribution map.

Fixtures are synthetic interface-development data. They are not model output
and must never be quoted as evaluation evidence.

---

## Project tree

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts                  dev proxy + preview-host allowlist
├── tailwind.config.ts              maps CSS custom properties -> utilities
├── postcss.config.js
├── .env.example
├── README.md
├── DESIGN.md
├── scripts/
│   ├── check-contrast.mjs          WCAG audit over tokens.css
│   └── smoke-render.mjs            SSR render + mandatory-copy assertions
└── src/
    ├── main.tsx
    ├── App.tsx                     layout, state machine, focus + live region
    ├── vite-env.d.ts
    ├── styles/
    │   ├── tokens.css              every colour in the product
    │   ├── animations.css          keyframes + motion utilities
    │   └── index.css               Tailwind layers + base/component classes
    ├── types/detection.ts          DetectResponse, SignalOutput, Quality, Verdict
    ├── api/client.ts               typed fetch, AbortController, error mapping
    ├── lib/
    │   ├── copy.ts                 all verbatim strings + banned-phrase guard
    │   ├── verdict.ts              verdict styles, band policy, direction styles
    │   ├── quality.ts              §5.1 thresholds -> warning list + severity
    │   ├── validateImage.ts        magic bytes, dimensions, APNG, preview
    │   ├── png.ts                  tEXt chunk writer for the heatmap download
    │   ├── motion.ts               useGrow + reduced-motion detection
    │   └── signalDocs.ts           Reason Code Explorer content
    ├── mocks/
    │   ├── fixtures.ts
    │   └── heatmaps.ts             base64 placeholder attribution maps
    └── components/
        ├── UploadPanel.tsx         ImagePreview.tsx      QualityWarnings.tsx
        ├── ResultCard.tsx          ProbabilityBar.tsx    ConfidenceBadge.tsx
        ├── BandIndicator.tsx       UncertaintyBanner.tsx WhatIfSlider.tsx
        ├── SignalList.tsx          SignalRow.tsx         InapplicableSignalRow.tsx
        ├── SignalRadar.tsx         HeatmapViewer.tsx     VersionInfo.tsx
        ├── PrivacyNotice.tsx       EmptyState.tsx        ErrorState.tsx
        └── ui/                     Tabs.tsx  Tooltip.tsx  Disclosure.tsx
                                    Spinner.tsx  Skeleton.tsx  Reveal.tsx  Icon.tsx
```

---

## Layout

Desktop (≥1024px) is two columns, 40 / 60:

| Left (40%) | Right (60%) |
| --- | --- |
| `UploadPanel` | `ResultCard` — verdict, probability, confidence, band |
| `ImagePreview` | `ManualReviewPanel` — the human decision |
| `QualityWarnings` | `SignalList` |
| | `HeatmapViewer` |
| | `VersionInfo` |

`PrivacyNotice` is pinned full-width at the bottom of the page. Below 1024px
the grid collapses to a single column in that same reading order; the internal
breakpoint at 768px (`sm:`) relaxes padding and lets header controls wrap.

---

## API contract

`POST ${VITE_API_BASE}/v1/detect`, `multipart/form-data`, field name `file`.

Response types live in `src/types/detection.ts`. The required fields mirror
`frebi.md` §13 exactly. A few optional fields from the fuller contract in
`PLANS/08-api-frontend.md` (`threshold_version`, `calibration_version`,
`top_drivers`, `band`, `region_scores`, `model_info`) are typed as optional so
the UI degrades honestly rather than inventing values — a missing
`threshold_version` renders as *not reported*, and a missing `band` renders an
explicitly-labelled illustrative default.

Error handling (§9.2), all in `src/api/client.ts`:

| Condition | Behaviour |
| --- | --- |
| `400`–`499` | Render the server's own `detail` (string, list, or `{msg}` list). |
| `500`+ | `"An unexpected error occurred. Please try again."` |
| Timeout (30s) | `"Request timed out. Check your connection and try again."` |
| Network failure | Same timeout copy — the reviewer's remedy is identical. |

---

## frebi.md §14 integration checklist

| Checklist item | Satisfied by |
| --- | --- |
| UploadPanel connected to `/v1/detect` | `components/UploadPanel.tsx` → `App.tsx#runDetection` → `api/client.ts#detect` |
| Verdict displayed with correct colour and label | `components/ResultCard.tsx`, `lib/verdict.ts#VERDICT_STYLE`, `styles/tokens.css` `--v-*-anchor` |
| Probability text follows mandatory format | `lib/copy.ts#probabilitySentence`, rendered in `components/ProbabilityBar.tsx` |
| Confidence level badge shown | `components/ConfidenceBadge.tsx`, strings in `lib/copy.ts#CONFIDENCE_BADGE` |
| Quality warnings displayed per `quality` dict | `components/QualityWarnings.tsx`, thresholds in `lib/quality.ts` |
| Signal explanations rendered for applicable signals | `components/SignalList.tsx` → `SignalRow.tsx`; skipped ones in `InapplicableSignalRow.tsx` |
| Heatmap viewer with limitation notice | `components/HeatmapViewer.tsx`, notice from `lib/copy.ts#HEATMAP_LIMITATION` |
| Model version shown | `components/VersionInfo.tsx` |
| Persistent privacy notice at bottom | `components/PrivacyNotice.tsx`, mounted in `App.tsx` outside `<main>` |
| All error states handled | `components/ErrorState.tsx`, `api/client.ts`, `lib/validateImage.ts`, `lib/copy.ts#UPLOAD_ERROR` / `#API_ERROR` |
| Accessibility requirements met | See the section below; audited by `scripts/check-contrast.mjs` |
| Download heatmap button works | `components/HeatmapViewer.tsx#onDownload` → `lib/png.ts#withPngTextMetadata` |
| Version info displayed | `components/VersionInfo.tsx` (model / threshold / calibration + hover tooltip) |

### Requirement coverage beyond the checklist

| Section | Where |
| --- | --- |
| §2.2 magic bytes, size, dimensions, multi-frame | `lib/validateImage.ts` |
| §2.3 400×400 preview + "Validating…" spinner | `lib/validateImage.ts#buildPreview`, `components/UploadPanel.tsx` |
| §3.3 inapplicable signals with reason | `components/InapplicableSignalRow.tsx` |
| §4.1 four heatmap views | `components/HeatmapViewer.tsx` + `ui/Tabs.tsx` |
| §4.3 limitation in download metadata | `lib/png.ts` (PNG `tEXt` chunks, CRC-checked) |
| §5.2 quality summary bar | `components/QualityWarnings.tsx` |
| §6.2 model info tooltip | `components/VersionInfo.tsx` + `ui/Tooltip.tsx` |
| §7.2 per-result warning | `components/ResultCard.tsx`, `components/ErrorState.tsx` |
| §8.1 band indicator | `components/BandIndicator.tsx` |
| §8.2 uncertainty score + interpretation | `components/UncertaintyBanner.tsx` |
| §9.3 empty / loading state | `components/EmptyState.tsx` |
| §11 What-if Slider | `components/WhatIfSlider.tsx` (collapsed, labelled illustrative) |
| §11 Reason Code Explorer | `components/SignalRow.tsx` + `lib/signalDocs.ts` |
| §11 Signal Radar Chart | `components/SignalRadar.tsx`, rendered at the top of `SignalList` |
| Manual reviewer decision | `components/ManualReviewPanel.tsx` |

## Manual review

`FAREBI.md` is emphatic that the detector is a risk signal and never an
autonomous rejection engine. That only means something if the human judgement
has somewhere to land, so `ManualReviewPanel` gives the reviewer three
outcomes — **Genuine**, **Manipulated**, **Escalate** — and treats the result
as authoritative over the model.

Two deliberate frictions:

- **Overriding the detector requires a written reason.** Disagreements between
  a model and a trained reviewer are the single most valuable events this
  system produces, and an unexplained one is worthless six weeks later. When
  the decision contradicts the verdict, focus jumps straight to the note field
  and *Copy decision record* refuses until it is filled in.
- **The record names the human as its author.** *Copy decision record* emits a
  plain-text audit block with the request ID, the detector's estimate, all
  three version strings, the reviewer's decision, whether it agreed or
  overrode, and the reason — under a heading that marks the reviewer decision
  as the authoritative outcome. It can never be mistaken for model output.

Where the detector declined to decide (`uncertain`, `unable_to_assess`) the
panel says there is no position to agree or disagree with, rather than
inventing one. The decision resets on every new capture; nothing is persisted,
because retention would need its own lawful basis.

The Social Media Recompression Simulator from §11 is **not** implemented: it
would need a server round trip per variant to say anything truthful, and a
client-side canvas approximation of Instagram's encoder would misrepresent
robustness rather than demonstrate it.

## Motion

Motion is a thin layer in `src/styles/animations.css`, driven by three tokens
(`--motion`, `--motion-slow`, `--motion-bar`) and two easing curves.

Three rules govern it:

1. **Motion carries meaning** — arrival (cards cascade in), magnitude (bars and
   the band marker travel from zero so you see *where they landed*), or state
   change (tab panels crossfade, expanded panels slide).
2. **Nothing loops** except genuine progress indicators: the upload spinner,
   the skeleton shimmer, and the scan line on the empty-state illustration,
   which stops existing the moment there is anything else to look at.
3. **Nothing animates a number a reviewer reads.** Bars grow; the figures
   beside them are correct on the first painted frame. A probability counting
   up from 0.00 to 0.64 is a misread waiting to happen, so `useGrow` in
   `lib/motion.ts` is deliberately only ever applied to widths and positions.

`prefers-reduced-motion: reduce` zeroes all three motion tokens *and* hard
disables every keyframe animation and hover transform, in both
`animations.css` and `index.css`.

---

## Accessibility

- **Never colour alone.** Every verdict carries a glyph (`✓ ✕ ? –`) and a text
  label; every signal direction carries an arrow *and* the words "toward fake"
  / "toward real" / "neutral"; the quality bar carries a glyph and one of
  "All checks passed" / "Warnings" / "Critical".
- **Contrast.** All 24 text/background token pairs are ≥ 4.5:1, verified by
  `npm run check:contrast` against `tokens.css` itself.
- **Focus management.** When a result arrives, focus moves to the verdict
  heading (`tabIndex={-1}`); when a request fails, it moves to the error
  heading. A skip link jumps straight to the result column.
- **Live region.** One `aria-live="polite"` status region announces the verdict
  and the full probability sentence, or the failure message.
- **Heatmap.** Each view has an `aria-label` naming the current mode; the
  attribution legend and the region-score table are described in words; the
  region view is a real `<table>` with a caption.
- **Keyboard.** Tabs implement WAI-ARIA roving focus with arrow/Home/End keys
  and manual activation. The tooltip opens on focus and closes on Escape, and
  its content is always wired up via `aria-describedby`.
- **Reduced motion.** `prefers-reduced-motion` zeroes the motion token and
  disables all transitions and the spinner animation.

---

## Deliberate omissions

No auth, no routing, no analytics, no telemetry, no service worker. The
console is a single-purpose review surface; anything that persists or
transmits reviewer behaviour would need its own lawful basis under the
retention rules in `FAREBI.md`.
