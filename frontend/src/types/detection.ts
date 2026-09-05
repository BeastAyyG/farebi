/**
 * Wire types for the Farebi detect API.
 *
 * The required fields mirror `frebi.md` §13 exactly. A small number of
 * optional fields from the fuller contract in `PLANS/08-api-frontend.md`
 * (threshold/calibration versions, fusion drivers, the conformal band) are
 * declared as optional so the UI degrades gracefully whether or not the
 * backend sends them.
 */

export type Verdict = 'likely_real' | 'likely_fake' | 'uncertain' | 'unable_to_assess';

export type ConfidenceLevel = 'low' | 'medium' | 'high';

export type SignalDirection = 'toward_fake' | 'toward_real' | 'toward_uncertain' | 'neutral';

export type CaptureType = 'selfie' | 'document' | 'unknown';

/** One entry from the `signals/` registry, as rendered by SignalList. */
export interface SignalOutput {
  /** Canonical reason code, e.g. "FFT_FREQUENCY". */
  code: string;
  direction: SignalDirection;
  /** Magnitude in [0, 1]. Not a probability of fakery. */
  strength: number;
  /** Plain-language explanation shown to the reviewer. */
  message: string;
  /** Mandatory: what else could produce the same measurement. */
  limitation: string;
  /** Absent means applicable (backend default). */
  applicable?: boolean;
  /** Why the signal could not run, keyed by quality indicator. */
  quality?: Quality;
  /** Human-readable reason a signal was skipped. */
  not_applicable_reason?: string;
}

/** Capture quality indicators (`frebi.md` §5.1). */
export interface Quality {
  face_found?: boolean;
  face_count?: number;
  /** Higher is blurrier. Warn above 0.3. */
  blur_score?: number;
  face_resolution_ok?: boolean;
  face_px?: number;
  eye_px?: number;
  /** Normalised exposure in [0, 1]; extremes are flagged. */
  exposure?: number;
  /** Eye-region overlap; below 0.5 suggests occlusion. */
  iou?: number;
  [key: string]: unknown;
}

/** Per-region attribution scores (`frebi.md` §4.1, region_scores view). */
export interface RegionScore {
  region: 'forehead' | 'eyes' | 'nose' | 'mouth' | 'chin' | string;
  score: number;
  direction?: SignalDirection;
}

/** Fusion driver (optional extension from PLANS/08). */
export interface TopDriver {
  signal: string;
  push: 'fake' | 'real' | 'uncertain';
  weight: number;
}

/** Conformal decision band (optional extension; see configs/thresholds.yaml). */
export interface DecisionBand {
  q_lo: number;
  q_hi: number;
}

export interface ModelInfo {
  architecture?: string;
  training_data?: string;
  last_updated?: string;
  weights_sha256?: string;
}

/** The response body of `POST /v1/detect`. */
export interface DetectResponse {
  request_id: string;
  verdict: Verdict;
  /** Calibrated probability in [0, 1]. Rendered as `0.82`, never as a percent. */
  fake_probability: number;
  confidence_level: ConfidenceLevel;
  /** Pipeline uncertainty in [0, 1]. */
  uncertainty_score: number;
  capture_type: CaptureType;
  signals: SignalOutput[];
  quality: Quality;
  /** Bare base64 PNG (no data: prefix) or null when explanation is unavailable. */
  heatmap_base64: string | null;
  warnings: string[];
  model_version: string;

  // --- optional extensions -------------------------------------------------
  threshold_version?: string;
  calibration_version?: string;
  top_drivers?: TopDriver[];
  band?: DecisionBand;
  region_scores?: RegionScore[];
  model_info?: ModelInfo;
}

/** Normalised failure surfaced to the UI. */
export interface DetectError {
  kind: 'validation' | 'http_400' | 'http_500' | 'timeout' | 'network';
  /** Message already resolved to the exact §9 copy. */
  message: string;
  status?: number;
}

export type HeatmapView = 'original' | 'attribution' | 'overlay' | 'region_scores';
