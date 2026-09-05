/**
 * Every user-visible string that `frebi.md` fixes verbatim.
 *
 * Rules enforced here (and by `assertNoBannedPhrase` in dev):
 *  - no percent signs on the probability,
 *  - no "guaranteed" / "certain" / "proven" / "detected a deepfake",
 *  - limitations are never optional.
 *
 * Do not paraphrase anything in this file. If the spec changes, change it here
 * and nowhere else.
 */

import type { ConfidenceLevel, Verdict } from '../types/detection';

/* ---------------------------------------------------------------- §1.1 --- */

export const VERDICT_LABEL: Record<Verdict, string> = {
  likely_real: 'Likely Real',
  likely_fake: 'Likely Fake',
  uncertain: 'Uncertain',
  unable_to_assess: 'Unable to Assess',
};

/* ---------------------------------------------------------------- §1.2 --- */

/**
 * The mandatory probability sentence.
 *
 * > "Estimated manipulation probability: 0.82. Confidence: medium.
 * >  The image should be manually reviewed."
 *
 * The probability is always fixed to two decimal places and never rendered as
 * a percentage.
 */
export function probabilitySentence(
  fakeProbability: number,
  confidenceLevel: ConfidenceLevel,
): string {
  return `Estimated manipulation probability: ${formatProbability(
    fakeProbability,
  )}. Confidence: ${confidenceLevel}. The image should be manually reviewed.`;
}

/** `0.82` — two decimals, clamped to [0, 1], never a percent. */
export function formatProbability(value: number): string {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));
  return clamped.toFixed(2);
}

/* ---------------------------------------------------------------- §1.3 --- */

export const CONFIDENCE_BADGE: Record<ConfidenceLevel, string> = {
  low: 'Low confidence — result should be manually reviewed',
  medium: 'Medium confidence — proceed with caution',
  high: 'High confidence — result may be trusted',
};

/* ---------------------------------------------------------------- §2.3 --- */

export const VALIDATING_LABEL = 'Validating…';

/* ---------------------------------------------------------------- §3.3 --- */

export const SIGNAL_NOT_APPLICABLE =
  'Signal not applicable — eyes too small / no video / no GPS';

/* ---------------------------------------------------------------- §4.2 --- */

export const HEATMAP_LIMITATION =
  'This heatmap shows pixel areas the model focused on. It is not definitive proof of manipulation. Similar patterns can be caused by lighting, background, or compression. Always combine with manual review.';

/* ---------------------------------------------------------------- §5.1 --- */

/** Warning bodies. The "⚠" glyph is rendered separately and aria-hidden so the
 *  screen-reader text stays clean while the printed string matches the spec. */
export const QUALITY_WARNING = {
  blur: 'Image is blurry — may affect accuracy',
  faceResolution: 'Face is small (< 40px) — consider moving closer',
  eyePx: 'Eyes too small for some signals',
  exposure: 'Poor exposure — result may be unreliable',
  iou: 'Face partially obscured',
} as const;

export const QUALITY_SUMMARY = {
  pass: 'All checks passed',
  warn: 'Warnings',
  fail: 'Critical',
} as const;

/* ---------------------------------------------------------------- §7 ----- */

export const PRIVACY_NOTICE_LEAD = 'Important:';

export const PRIVACY_NOTICE_BODY =
  'This detector analyzes image manipulation only. It does not verify liveness, identity ownership, or document authenticity. Results should be combined with manual review and capture/liveness controls per NIST guidelines. Uploaded images are deleted after inference by default.';

export const PER_RESULT_WARNING =
  'This detector does not verify liveness or identity ownership. Result should be manually reviewed.';

/* ---------------------------------------------------------------- §8.2 --- */

export const UNCERTAINTY_INTERPRETATION = {
  low: 'Low uncertainty',
  medium: 'Medium',
  high: 'High — strongly recommend manual review',
} as const;

/* ---------------------------------------------------------------- §9.1 --- */

export const UPLOAD_ERROR = {
  tooLarge: 'File size exceeds limit of 10MB',
  invalidFormat: 'Only JPEG and PNG are supported',
  corrupt: 'Could not read uploaded file — it may be corrupt',
  multiFrame: 'Multi-frame files are not supported',
  noFace: 'No face detected in image — unable to assess',
  faceTooSmall: 'Face is too small — move closer and try again',
} as const;

/** Dimension ceiling is a UI pre-check; the API is authoritative. */
export const UPLOAD_ERROR_DIMENSIONS = 'Image dimensions exceed 2048×2048';

/* ---------------------------------------------------------------- §9.2 --- */

export const API_ERROR = {
  server: 'An unexpected error occurred. Please try again.',
  timeout: 'Request timed out. Check your connection and try again.',
  network: 'Request timed out. Check your connection and try again.',
} as const;

/* ---------------------------------------------------------------- §9.3 --- */

export const EMPTY_STATE_TITLE = 'Upload an image to begin detection';
export const EMPTY_STATE_HINT = 'JPEG or PNG, under 10MB';

/* ---------------------------------------------------------------- guard -- */

const BANNED = [
  'guaranteed',
  'certainly',
  'proven',
  'proof of manipulation is',
  'detected a deepfake',
];

/**
 * Dev-only tripwire mirroring the backend's banned-phrase test. Any rendered
 * sentence that slips into marketing certainty fails loudly in development
 * rather than quietly shipping.
 */
export function assertNoBannedPhrase(text: string, where: string): void {
  if (!import.meta.env.DEV) return;
  const lower = text.toLowerCase();
  for (const phrase of BANNED) {
    if (lower.includes(phrase)) {
      // eslint-disable-next-line no-console
      console.error(`[farebi] banned phrase "${phrase}" rendered in ${where}: ${text}`);
    }
  }
  if (/\d\s?%/.test(text)) {
    // eslint-disable-next-line no-console
    console.error(`[farebi] percentage rendered in ${where}: ${text}`);
  }
}
