/**
 * Fixture responses for `VITE_MOCK_API=true`.
 *
 * One `DetectResponse` per verdict, plus one canned failure per §9 error state,
 * so the whole UI — including every branch of QualityWarnings, SignalList and
 * HeatmapViewer — is demoable with no backend running.
 *
 * These are synthetic numbers for interface development. They are not model
 * output and must never be presented as evaluation evidence.
 */

import type { DetectError, DetectResponse, SignalOutput } from '../types/detection';
import { API_ERROR, UPLOAD_ERROR } from '../lib/copy';
import { HEATMAP_COOL, HEATMAP_HOT, HEATMAP_MIXED } from './heatmaps';

const MODEL_VERSION = 'kyc-detector-0.1.0';
const THRESHOLD_VERSION = 'conformal-q0.05-v1';
const CALIBRATION_VERSION = 'temperature-v2';

const MODEL_INFO = {
  architecture: 'CLIP ViT-L/14 backbone + linear probe head',
  training_data:
    'FaceForensics++, CelebDF-v2 and an internal KYC capture set, degraded through the KYC pipeline (recompression, downscale, screen replay).',
  last_updated: '2026-08-21',
  weights_sha256: '9f2c41ab7d0e5c86b3a1f04e77c9d2158be6a3f0c4d97e21b58a0cf3d6e4718b',
};

/* --------------------------------------------------------------- signals -- */

const fft = (strength: number, direction: SignalOutput['direction']): SignalOutput => ({
  code: 'FFT_FREQUENCY',
  direction,
  strength,
  message:
    'The frequency spectrum of this image shows periodic structure of the kind often left by generative upsampling.',
  limitation:
    'Similar patterns can also be caused by image recompression, digital zoom, or screenshotting.',
  applicable: true,
});

const clip = (strength: number, direction: SignalOutput['direction']): SignalOutput => ({
  code: 'CLIP_CLASSIFIER',
  direction,
  strength,
  message: 'The visual classifier found patterns associated with manipulated images.',
  limitation:
    'Similar patterns can also be caused by background removal or image compression.',
  applicable: true,
});

const geometry = (strength: number, direction: SignalOutput['direction']): SignalOutput => ({
  code: 'FACE_GEOMETRY',
  direction,
  strength,
  message:
    'Landmark proportions across the face fall within the range measured on authentic captures.',
  limitation:
    'Wide-angle selfie lenses, extreme head pose, and natural asymmetry all shift these proportions.',
  applicable: true,
});

const eyeReflectionInapplicable: SignalOutput = {
  code: 'EYE_REFLECTION',
  direction: 'neutral',
  strength: 0,
  message: 'Corneal highlights were not compared because the eye region was too small to resolve.',
  limitation:
    'A skipped signal is not evidence in either direction. It simply means this measurement was unavailable.',
  applicable: false,
  not_applicable_reason: 'eye_px 22 is below the 40px minimum for this signal',
  quality: { eye_px: 22 },
};

const eyeReflection = (strength: number, direction: SignalOutput['direction']): SignalOutput => ({
  code: 'EYE_REFLECTION',
  direction,
  strength,
  message:
    'The specular highlights in the left and right eye are consistent with a single shared light source.',
  limitation:
    'Glasses, multiple real light sources, and low eye resolution can all break this agreement in authentic photos.',
  applicable: true,
});

const metadataUnavailable: SignalOutput = {
  code: 'METADATA_UNAVAILABLE',
  direction: 'neutral',
  strength: 0,
  message:
    'No trustworthy capture metadata was available. This is not evidence of manipulation.',
  limitation:
    'Messaging apps and web uploads routinely strip metadata from authentic photographs.',
  applicable: true,
};

/* ------------------------------------------------------------- responses -- */

export const FIXTURE_LIKELY_REAL: DetectResponse = {
  request_id: '1b6a5f43-9d0c-4a71-8f2e-0c4b7d9a1e33',
  verdict: 'likely_real',
  fake_probability: 0.11,
  confidence_level: 'high',
  uncertainty_score: 0.12,
  capture_type: 'selfie',
  signals: [
    clip(0.72, 'toward_real'),
    geometry(0.58, 'toward_real'),
    eyeReflection(0.44, 'toward_real'),
    fft(0.19, 'neutral'),
    metadataUnavailable,
  ],
  quality: {
    face_found: true,
    face_count: 1,
    blur_score: 0.09,
    face_resolution_ok: true,
    face_px: 386,
    eye_px: 61,
    exposure: 0.52,
    iou: 0.94,
  },
  heatmap_base64: HEATMAP_COOL,
  warnings: [],
  model_version: MODEL_VERSION,
  threshold_version: THRESHOLD_VERSION,
  calibration_version: CALIBRATION_VERSION,
  band: { q_lo: 0.35, q_hi: 0.65 },
  top_drivers: [
    { signal: 'CLIP_CLASSIFIER', push: 'real', weight: 0.41 },
    { signal: 'FACE_GEOMETRY', push: 'real', weight: 0.22 },
  ],
  region_scores: [
    { region: 'forehead', score: 0.12, direction: 'toward_real' },
    { region: 'eyes', score: 0.18, direction: 'toward_real' },
    { region: 'nose', score: 0.09, direction: 'toward_real' },
    { region: 'mouth', score: 0.14, direction: 'toward_real' },
    { region: 'chin', score: 0.07, direction: 'toward_real' },
  ],
  model_info: MODEL_INFO,
};

export const FIXTURE_LIKELY_FAKE: DetectResponse = {
  request_id: '8ae1bf1c-3a28-4f58-a850-53a65db12c17',
  verdict: 'likely_fake',
  fake_probability: 0.87,
  confidence_level: 'medium',
  uncertainty_score: 0.24,
  capture_type: 'selfie',
  signals: [
    clip(0.91, 'toward_fake'),
    fft(0.78, 'toward_fake'),
    {
      code: 'TEXTURE_INCONSISTENCY',
      direction: 'toward_fake',
      strength: 0.63,
      message:
        'Skin micro-texture is smoother in the central face region than at the jawline and neck.',
      limitation:
        'Beauty filters, denoising, and low-light capture produce the same smoothing in authentic photos.',
      applicable: true,
    },
    geometry(0.31, 'neutral'),
    eyeReflectionInapplicable,
    metadataUnavailable,
  ],
  quality: {
    face_found: true,
    face_count: 1,
    blur_score: 0.21,
    face_resolution_ok: true,
    face_px: 244,
    eye_px: 22,
    exposure: 0.49,
    iou: 0.88,
  },
  heatmap_base64: HEATMAP_HOT,
  warnings: [
    'One signal was unavailable for this capture, so the result rests on fewer measurements than usual.',
  ],
  model_version: MODEL_VERSION,
  threshold_version: THRESHOLD_VERSION,
  calibration_version: CALIBRATION_VERSION,
  band: { q_lo: 0.35, q_hi: 0.65 },
  top_drivers: [
    { signal: 'CLIP_CLASSIFIER', push: 'fake', weight: 0.46 },
    { signal: 'FFT_FREQUENCY', push: 'fake', weight: 0.29 },
    { signal: 'TEXTURE_INCONSISTENCY', push: 'fake', weight: 0.17 },
  ],
  region_scores: [
    { region: 'forehead', score: 0.44, direction: 'toward_fake' },
    { region: 'eyes', score: 0.81, direction: 'toward_fake' },
    { region: 'nose', score: 0.66, direction: 'toward_fake' },
    { region: 'mouth', score: 0.72, direction: 'toward_fake' },
    { region: 'chin', score: 0.38, direction: 'toward_fake' },
  ],
  model_info: MODEL_INFO,
};

export const FIXTURE_UNCERTAIN: DetectResponse = {
  request_id: '4c07e2d9-51b8-4f0a-9c63-2ad8e5b41f70',
  verdict: 'uncertain',
  fake_probability: 0.64,
  confidence_level: 'low',
  uncertainty_score: 0.31,
  capture_type: 'selfie',
  signals: [
    clip(0.57, 'toward_fake'),
    fft(0.41, 'toward_fake'),
    geometry(0.49, 'toward_real'),
    eyeReflectionInapplicable,
    {
      code: 'MODEL_DISAGREEMENT',
      direction: 'toward_uncertain',
      strength: 0.58,
      message:
        'The visual classifier and the geometry signal point in opposite directions on this capture.',
      limitation:
        'Disagreement is expected near the decision band and does not by itself indicate manipulation.',
      applicable: true,
    },
    metadataUnavailable,
  ],
  quality: {
    face_found: true,
    face_count: 1,
    blur_score: 0.34,
    face_resolution_ok: true,
    face_px: 168,
    eye_px: 28,
    exposure: 0.71,
    iou: 0.62,
  },
  heatmap_base64: HEATMAP_MIXED,
  warnings: ['The result is uncertain and should be manually reviewed.'],
  model_version: MODEL_VERSION,
  threshold_version: THRESHOLD_VERSION,
  calibration_version: CALIBRATION_VERSION,
  band: { q_lo: 0.35, q_hi: 0.65 },
  top_drivers: [
    { signal: 'CLIP_CLASSIFIER', push: 'fake', weight: 0.33 },
    { signal: 'FACE_GEOMETRY', push: 'real', weight: 0.21 },
    { signal: 'MODEL_DISAGREEMENT', push: 'uncertain', weight: 0.19 },
  ],
  region_scores: [
    { region: 'forehead', score: 0.31, direction: 'toward_fake' },
    { region: 'eyes', score: 0.52, direction: 'toward_fake' },
    { region: 'nose', score: 0.27, direction: 'toward_real' },
    { region: 'mouth', score: 0.48, direction: 'toward_fake' },
    { region: 'chin', score: 0.22, direction: 'toward_real' },
  ],
  model_info: MODEL_INFO,
};

export const FIXTURE_UNABLE: DetectResponse = {
  request_id: 'd9f4c8a2-6e13-49bb-b0d7-3f81c5e2a904',
  verdict: 'unable_to_assess',
  fake_probability: 0.5,
  confidence_level: 'low',
  uncertainty_score: 0.82,
  capture_type: 'unknown',
  signals: [
    {
      code: 'FACE_TOO_SMALL',
      direction: 'neutral',
      strength: 0,
      message:
        'A face was located but is too small to run the forensic signals reliably.',
      limitation:
        'This is a capture-quality outcome, not a finding about the image. Re-capture at a closer distance.',
      applicable: true,
    },
    { ...eyeReflectionInapplicable, not_applicable_reason: 'eye_px 11 is below the 40px minimum' },
    {
      code: 'CLIP_CLASSIFIER',
      direction: 'neutral',
      strength: 0,
      message: 'The visual classifier was not run because the face crop was below its input size.',
      limitation:
        'A skipped signal carries no information about whether the image was manipulated.',
      applicable: false,
      not_applicable_reason: 'face_px 31 is below the 40px minimum',
      quality: { face_px: 31 },
    },
    metadataUnavailable,
  ],
  quality: {
    face_found: true,
    face_count: 1,
    blur_score: 0.47,
    face_resolution_ok: false,
    face_px: 31,
    eye_px: 11,
    exposure: 0.16,
    iou: 0.41,
  },
  heatmap_base64: null,
  warnings: [
    'Capture quality was too low to assess this image. No manipulation estimate is being reported.',
  ],
  model_version: MODEL_VERSION,
  threshold_version: THRESHOLD_VERSION,
  calibration_version: CALIBRATION_VERSION,
  band: { q_lo: 0.35, q_hi: 0.65 },
  top_drivers: [],
  model_info: MODEL_INFO,
};

/* ---------------------------------------------------------------- errors -- */

export const FIXTURE_ERRORS: Record<string, DetectError> = {
  no_face: { kind: 'http_400', status: 400, message: UPLOAD_ERROR.noFace },
  face_too_small: { kind: 'http_400', status: 400, message: UPLOAD_ERROR.faceTooSmall },
  corrupt: { kind: 'http_400', status: 400, message: UPLOAD_ERROR.corrupt },
  multi_frame: { kind: 'http_400', status: 400, message: UPLOAD_ERROR.multiFrame },
  server_error: { kind: 'http_500', status: 500, message: API_ERROR.server },
  timeout: { kind: 'timeout', message: API_ERROR.timeout },
};

/* -------------------------------------------------------------- selector -- */

export type MockScenario =
  | 'likely_real'
  | 'likely_fake'
  | 'uncertain'
  | 'unable_to_assess'
  | keyof typeof FIXTURE_ERRORS;

export const MOCK_SCENARIOS: { id: MockScenario; label: string }[] = [
  { id: 'likely_real', label: 'Likely Real' },
  { id: 'likely_fake', label: 'Likely Fake' },
  { id: 'uncertain', label: 'Uncertain' },
  { id: 'unable_to_assess', label: 'Unable to Assess' },
  { id: 'no_face', label: 'Error · no face' },
  { id: 'face_too_small', label: 'Error · face too small' },
  { id: 'corrupt', label: 'Error · corrupt file' },
  { id: 'multi_frame', label: 'Error · multi-frame' },
  { id: 'server_error', label: 'Error · 500' },
  { id: 'timeout', label: 'Error · timeout' },
];

export const FIXTURE_RESPONSES: Record<string, DetectResponse> = {
  likely_real: FIXTURE_LIKELY_REAL,
  likely_fake: FIXTURE_LIKELY_FAKE,
  uncertain: FIXTURE_UNCERTAIN,
  unable_to_assess: FIXTURE_UNABLE,
};

/** Resolves a scenario to either a response or a thrown-style error object. */
export function resolveFixture(
  scenario: MockScenario,
): { response: DetectResponse } | { error: DetectError } {
  const response = FIXTURE_RESPONSES[scenario];
  if (response) return { response: { ...response, request_id: randomId() } };
  const error = FIXTURE_ERRORS[scenario];
  return { error: error ?? FIXTURE_ERRORS.server_error };
}

function randomId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `mock-${Math.random().toString(16).slice(2, 10)}`;
}
