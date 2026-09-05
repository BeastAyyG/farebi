/**
 * Derives the §5 quality warning list and summary severity from the `quality`
 * dict. Thresholds mirror `frebi.md` §5.1 exactly.
 */

import type { Quality, Verdict } from '../types/detection';
import { QUALITY_WARNING, UPLOAD_ERROR } from './copy';

export type QualitySeverity = 'pass' | 'warn' | 'fail';

export interface QualityWarning {
  id: string;
  /** Verbatim §5.1 text, without the leading glyph. */
  text: string;
  severity: 'warn' | 'fail';
  /** Mono detail such as `blur_score 0.42` for the reviewer's audit trail. */
  detail?: string;
}

export const BLUR_WARN_ABOVE = 0.3;
export const MIN_FACE_PX = 40;
export const MIN_EYE_PX = 40;
export const MIN_EYE_IOU = 0.5;
export const EXPOSURE_LOW = 0.2;
export const EXPOSURE_HIGH = 0.8;

function num(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

export function deriveQualityWarnings(quality: Quality | undefined): QualityWarning[] {
  if (!quality) return [];
  const out: QualityWarning[] = [];

  if (quality.face_found === false) {
    out.push({ id: 'no_face', text: UPLOAD_ERROR.noFace, severity: 'fail' });
  }

  if (typeof quality.face_count === 'number' && quality.face_count > 1) {
    out.push({
      id: 'multiple_faces',
      text: 'Multiple faces detected — the largest face was assessed',
      severity: 'warn',
      detail: `face_count ${quality.face_count}`,
    });
  }

  const blur = num(quality.blur_score);
  if (blur !== undefined && blur > BLUR_WARN_ABOVE) {
    out.push({
      id: 'blur',
      text: QUALITY_WARNING.blur,
      severity: 'warn',
      detail: `blur_score ${blur.toFixed(2)}`,
    });
  }

  const facePx = num(quality.face_px);
  const faceResolutionFailed =
    quality.face_resolution_ok === false || (facePx !== undefined && facePx < MIN_FACE_PX);
  if (faceResolutionFailed) {
    out.push({
      id: 'face_resolution',
      text: QUALITY_WARNING.faceResolution,
      severity: 'fail',
      detail: facePx !== undefined ? `face_px ${Math.round(facePx)}` : 'face_resolution_ok false',
    });
  }

  const eyePx = num(quality.eye_px);
  if (eyePx !== undefined && eyePx < MIN_EYE_PX) {
    out.push({
      id: 'eye_px',
      text: QUALITY_WARNING.eyePx,
      severity: 'warn',
      detail: `eye_px ${Math.round(eyePx)}`,
    });
  }

  const exposure = num(quality.exposure);
  if (exposure !== undefined && (exposure < EXPOSURE_LOW || exposure > EXPOSURE_HIGH)) {
    out.push({
      id: 'exposure',
      text: QUALITY_WARNING.exposure,
      severity: 'warn',
      detail: `exposure ${exposure.toFixed(2)}`,
    });
  }

  const iou = num(quality.iou);
  if (iou !== undefined && iou < MIN_EYE_IOU) {
    out.push({
      id: 'iou',
      text: QUALITY_WARNING.iou,
      severity: 'warn',
      detail: `iou ${iou.toFixed(2)}`,
    });
  }

  return out;
}

/**
 * Summary severity for the §5.2 bar. `unable_to_assess` always reads as a
 * critical failure even when individual indicators look benign, because the
 * pipeline already refused to score the capture.
 */
export function qualitySeverity(
  warnings: QualityWarning[],
  verdict?: Verdict,
): QualitySeverity {
  if (verdict === 'unable_to_assess') return 'fail';
  if (warnings.some((w) => w.severity === 'fail')) return 'fail';
  if (warnings.length > 0) return 'warn';
  return 'pass';
}
