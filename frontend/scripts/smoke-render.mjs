#!/usr/bin/env node
/**
 * Render smoke test.
 *
 * Renders the full result view for every fixture verdict and every error
 * state through Vite's SSR pipeline, then asserts the guarantees frebi.md
 * treats as non-negotiable:
 *
 *   - the mandatory probability sentence appears exactly (§1.2)
 *   - no percentage is ever printed for a probability (§1.2)
 *   - no banned certainty language appears (§1.2)
 *   - the confidence badge, heatmap limitation, per-result warning and
 *     privacy notice are present verbatim (§1.3, §4.2, §7)
 *   - every applicable signal renders its limitation (§3.2)
 *
 * It catches component crashes too, which is why it runs before the build.
 *
 *   npm run check:render
 */

import { createServer } from 'vite';
import React from 'react';

const server = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'error',
});

let failures = 0;
const fail = (msg) => {
  failures += 1;
  console.error(`  FAIL  ${msg}`);
};

try {
  const { renderToStaticMarkup } = await import('react-dom/server');
  const fixtures = await server.ssrLoadModule('/src/mocks/fixtures.ts');
  const copy = await server.ssrLoadModule('/src/lib/copy.ts');
  const { ResultCard } = await server.ssrLoadModule('/src/components/ResultCard.tsx');
  const { SignalList } = await server.ssrLoadModule('/src/components/SignalList.tsx');
  const { HeatmapViewer } = await server.ssrLoadModule('/src/components/HeatmapViewer.tsx');
  const { VersionInfo } = await server.ssrLoadModule('/src/components/VersionInfo.tsx');
  const { QualityWarnings } = await server.ssrLoadModule('/src/components/QualityWarnings.tsx');
  const { PrivacyNotice } = await server.ssrLoadModule('/src/components/PrivacyNotice.tsx');
  const { ErrorState } = await server.ssrLoadModule('/src/components/ErrorState.tsx');
  const { EmptyState } = await server.ssrLoadModule('/src/components/EmptyState.tsx');

  const h = React.createElement;
  const clean = (s) =>
    s
      .replace(/&#x27;|&#39;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&amp;/g, '&')
      .replace(/&gt;/g, '>')
      .replace(/&lt;/g, '<');
  /** Tags become spaces — good for spotting stray tokens across elements. */
  const text = (html) => clean(html.replace(/<[^>]+>/g, ' ')).replace(/&nbsp;|\s+/g, ' ').trim();
  /** Tags vanish — reproduces the sentence a sighted reader actually sees when
   *  it is marked up inline with <strong> / <span>. */
  const tight = (html) => clean(html.replace(/<[^>]+>/g, '')).replace(/&nbsp;|\s+/g, ' ').trim();

  const BANNED = ['guaranteed', 'is certainly', 'proven fake', 'detected a deepfake'];

  console.log('Render smoke test\n');

  for (const [name, result] of Object.entries(fixtures.FIXTURE_RESPONSES)) {
    const html = renderToStaticMarkup(
      h(
        'div',
        null,
        h(QualityWarnings, { quality: result.quality, verdict: result.verdict }),
        h(ResultCard, {
          verdict: result.verdict,
          probability: result.fake_probability,
          confidence: result.confidence_level,
          signals: result.signals,
          result,
        }),
        h(SignalList, { signals: result.signals }),
        h(HeatmapViewer, {
          image: null,
          map: result.heatmap_base64,
          regionScores: result.region_scores,
          requestId: result.request_id,
          modelVersion: result.model_version,
        }),
        h(VersionInfo, {
          model: result.model_version,
          threshold: result.threshold_version,
          calibration: result.calibration_version,
          info: result.model_info,
        }),
        h(PrivacyNotice, null),
      ),
    );
    const body = text(html);
    const inline = tight(html);
    const assessable = result.verdict !== 'unable_to_assess';

    // §1.1 verdict label
    const label = copy.VERDICT_LABEL[result.verdict];
    if (!body.includes(label)) fail(`${name}: verdict label "${label}" missing`);

    // §1.2 mandatory sentence
    if (assessable) {
      const sentence = copy.probabilitySentence(
        result.fake_probability,
        result.confidence_level,
      );
      // Checked against the tag-tight rendering AND the bar's aria-label, so
      // both the sighted and the screen-reader path are covered.
      if (!inline.includes(sentence)) {
        fail(`${name}: mandatory probability sentence missing from visible text.\n        expected: ${sentence}`);
      }
      if (!html.includes(`aria-label="${sentence}"`)) {
        fail(`${name}: mandatory probability sentence missing from the bar aria-label`);
      }
      // §1.3 confidence badge
      const badge = copy.CONFIDENCE_BADGE[result.confidence_level];
      if (!body.includes(badge)) fail(`${name}: confidence badge "${badge}" missing`);
    }

    // §1.2 no percentages anywhere
    const pct = body.match(/\d+(\.\d+)?\s?%/g);
    if (pct) fail(`${name}: percentage rendered: ${pct.join(', ')}`);

    // §1.2 no certainty language
    for (const phrase of BANNED) {
      if (body.toLowerCase().includes(phrase)) fail(`${name}: banned phrase "${phrase}"`);
    }

    // §4.2 heatmap limitation, §7.2 per-result warning, §7.1 privacy banner
    if (!body.includes(copy.HEATMAP_LIMITATION)) fail(`${name}: heatmap limitation missing`);
    if (!body.includes(copy.PER_RESULT_WARNING)) fail(`${name}: per-result warning missing`);
    if (!body.includes(copy.PRIVACY_NOTICE_BODY)) fail(`${name}: privacy notice missing`);

    // §3.2 every applicable signal shows its limitation
    for (const signal of result.signals) {
      if (signal.applicable === false) continue;
      if (!body.includes(signal.limitation)) {
        fail(`${name}: limitation missing for signal ${signal.code}`);
      }
      if (!body.includes(signal.code)) fail(`${name}: signal code ${signal.code} missing`);
    }

    // §3.3 skipped signals are shown, not hidden
    if (result.signals.some((s) => s.applicable === false)) {
      if (!body.includes(copy.SIGNAL_NOT_APPLICABLE)) {
        fail(`${name}: inapplicable-signal notice missing`);
      }
    }

    // §6.1 all three versions
    for (const v of [result.model_version, result.threshold_version, result.calibration_version]) {
      if (v && !body.includes(v)) fail(`${name}: version "${v}" missing`);
    }

    console.log(`  ok    ${name.padEnd(18)} ${body.length} chars rendered`);
  }

  // §9 error states
  for (const [name, error] of Object.entries(fixtures.FIXTURE_ERRORS)) {
    const body = text(renderToStaticMarkup(h(ErrorState, { error })));
    if (!body.includes(error.message)) fail(`error ${name}: message missing`);
    if (!body.includes(copy.PER_RESULT_WARNING)) fail(`error ${name}: per-result warning missing`);
    console.log(`  ok    error:${name}`);
  }

  // §9.3 empty state
  const empty = text(renderToStaticMarkup(h(EmptyState, null)));
  if (!empty.includes(copy.EMPTY_STATE_TITLE)) fail('empty state: title missing');
  if (!empty.includes(copy.EMPTY_STATE_HINT)) fail('empty state: hint missing');
  console.log('  ok    empty state');
} finally {
  await server.close();
}

console.log();
if (failures > 0) {
  console.error(`${failures} assertion(s) failed.`);
  process.exit(1);
}
console.log('All render assertions passed.');
