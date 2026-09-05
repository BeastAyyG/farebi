/**
 * Verdict presentation metadata and the client-side band policy used by the
 * illustrative "What-if" slider.
 *
 * Colour is never the only channel: every verdict carries a glyph and a label.
 */

import type { ConfidenceLevel, DecisionBand, SignalDirection, Verdict } from '../types/detection';
import { VERDICT_LABEL } from './copy';

export interface VerdictStyle {
  label: string;
  /** Text/glyph equivalent so colour is never load-bearing. */
  glyph: '✓' | '✕' | '?' | '–';
  /** Tailwind classes bound to CSS tokens. */
  fill: string;
  ink: string;
  border: string;
  stripe: string;
  dot: string;
  /** Spoken description for the live region. */
  announce: string;
}

export const VERDICT_STYLE: Record<Verdict, VerdictStyle> = {
  likely_real: {
    label: VERDICT_LABEL.likely_real,
    glyph: '✓',
    fill: 'bg-verdict-real-fill',
    ink: 'text-verdict-real-ink',
    border: 'border-verdict-real-border',
    stripe: 'bg-verdict-real-anchor',
    dot: 'bg-verdict-real-anchor',
    announce: 'Verdict: Likely Real.',
  },
  likely_fake: {
    label: VERDICT_LABEL.likely_fake,
    glyph: '✕',
    fill: 'bg-verdict-fake-fill',
    ink: 'text-verdict-fake-ink',
    border: 'border-verdict-fake-border',
    stripe: 'bg-verdict-fake-anchor',
    dot: 'bg-verdict-fake-anchor',
    announce: 'Verdict: Likely Fake.',
  },
  uncertain: {
    label: VERDICT_LABEL.uncertain,
    glyph: '?',
    fill: 'bg-verdict-unc-fill',
    ink: 'text-verdict-unc-ink',
    border: 'border-verdict-unc-border',
    stripe: 'bg-verdict-unc-anchor',
    dot: 'bg-verdict-unc-anchor',
    announce: 'Verdict: Uncertain.',
  },
  unable_to_assess: {
    label: VERDICT_LABEL.unable_to_assess,
    glyph: '–',
    fill: 'bg-verdict-na-fill',
    ink: 'text-verdict-na-ink',
    border: 'border-verdict-na-border',
    stripe: 'bg-verdict-na-anchor',
    dot: 'bg-verdict-na-anchor',
    announce: 'Verdict: Unable to Assess.',
  },
};

/**
 * Fallback conformal band, used only when the API omits one.
 * `configs/thresholds.yaml` ships uncalibrated nulls, so the UI must never
 * assume a band is present.
 */
export const DEFAULT_BAND: DecisionBand = { q_lo: 0.35, q_hi: 0.65 };

export function resolveBand(band?: DecisionBand): DecisionBand {
  if (!band) return DEFAULT_BAND;
  const lo = clamp01(band.q_lo);
  const hi = clamp01(band.q_hi);
  return lo <= hi ? { q_lo: lo, q_hi: hi } : DEFAULT_BAND;
}

/**
 * Band policy from `frebi.md` §8.1.
 * `unable_to_assess` is a capture decision, not a probability decision, so it
 * is never produced here.
 */
export function verdictFromBand(pFake: number, band: DecisionBand): Verdict {
  if (pFake <= band.q_lo) return 'likely_real';
  if (pFake >= band.q_hi) return 'likely_fake';
  return 'uncertain';
}

export function isInBand(pFake: number, band: DecisionBand): boolean {
  return pFake > band.q_lo && pFake < band.q_hi;
}

/** §8.2 uncertainty interpretation buckets. */
export function uncertaintyBucket(score: number): 'low' | 'medium' | 'high' {
  if (score < 0.3) return 'low';
  if (score <= 0.6) return 'medium';
  return 'high';
}

export const CONFIDENCE_ORDER: ConfidenceLevel[] = ['low', 'medium', 'high'];

export interface DirectionStyle {
  arrow: '↑' | '↓' | '→';
  /** Written form, so the arrow is never the only cue. */
  label: string;
  ink: string;
  fill: string;
}

export const DIRECTION_STYLE: Record<SignalDirection, DirectionStyle> = {
  toward_fake: {
    arrow: '↑',
    label: 'toward fake',
    ink: 'text-terracotta-700',
    fill: 'bg-terracotta-500',
  },
  toward_real: {
    arrow: '↓',
    label: 'toward real',
    ink: 'text-blue-700',
    fill: 'bg-blue-500',
  },
  toward_uncertain: {
    arrow: '→',
    label: 'toward uncertain',
    ink: 'text-ochre-700',
    fill: 'bg-ochre-500',
  },
  neutral: {
    arrow: '→',
    label: 'neutral',
    ink: 'text-ink-3',
    fill: 'bg-line-strong',
  },
};

export function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

/** True when the signal should render in the applicable list. */
export function isApplicable(applicable: boolean | undefined): boolean {
  return applicable !== false;
}
