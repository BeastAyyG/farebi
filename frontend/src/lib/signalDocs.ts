/**
 * Reason Code Explorer content (§11).
 *
 * The API already ships `message` and `limitation` per signal — those are
 * authoritative and rendered verbatim. This table adds only the "what could
 * cause a false positive" list, which is reviewer training material, not a
 * model output. Unknown codes fall back to a generic, honest entry.
 */

export interface ReasonCodeDoc {
  /** Short human title for the code. */
  title: string;
  /** Which forensic family the signal belongs to. */
  family: string;
  /** Benign explanations that produce the same measurement. */
  falsePositives: string[];
  /** External docs anchor, resolved against the signal docs base. */
  slug: string;
}

export const SIGNAL_DOCS_BASE = 'https://github.com/BeastAyyG/farebi/blob/master/PLANS/';

const DOCS: Record<string, ReasonCodeDoc> = {
  FFT_FREQUENCY: {
    title: 'Frequency-domain artefact',
    family: 'Spectral forensics',
    slug: '04-signals-tier1.md#fft',
    falsePositives: [
      'Aggressive JPEG or WebP recompression, especially after messaging apps.',
      'Upscaling or downscaling with a resampling filter that leaves periodic ringing.',
      'Beauty filters and denoising applied in-camera by the phone.',
      'Screenshots, which resample the image to the display grid.',
    ],
  },
  FREQUENCY_ARTIFACT: {
    title: 'Frequency-domain artefact',
    family: 'Spectral forensics',
    slug: '04-signals-tier1.md#fft',
    falsePositives: [
      'Recompression by a social platform or chat client.',
      'Digital zoom and interpolation during capture.',
      'Aggressive in-camera sharpening.',
    ],
  },
  CLIP_CLASSIFIER: {
    title: 'Visual classifier response',
    family: 'Learned model',
    slug: '04-signals-tier1.md#vit-clip',
    falsePositives: [
      'Backgrounds removed or replaced, which the classifier reads as synthesis.',
      'Studio lighting and heavy retouching in an otherwise authentic photo.',
      'Subjects, poses, or camera hardware under-represented in training data.',
      'Unusual crops that leave little facial context.',
    ],
  },
  VISUAL_MODEL_FAKE_SIGNAL: {
    title: 'Visual classifier response',
    family: 'Learned model',
    slug: '04-signals-tier1.md#vit-clip',
    falsePositives: [
      'Out-of-distribution capture conditions the model has not seen.',
      'Background removal or synthetic backdrops.',
      'Strong colour grading applied by the camera app.',
    ],
  },
  FACE_GEOMETRY: {
    title: 'Facial geometry consistency',
    family: 'Landmark analysis',
    slug: '06-signals-tier3.md#geometry',
    falsePositives: [
      'Wide-angle selfie lenses, which distort proportions near the frame edge.',
      'Extreme head pose or the subject looking away from the lens.',
      'Glasses, masks, or hair occluding landmark positions.',
      'Genuine facial asymmetry, which is common and normal.',
    ],
  },
  GEOMETRY_INCONSISTENCY: {
    title: 'Facial geometry consistency',
    family: 'Landmark analysis',
    slug: '06-signals-tier3.md#geometry',
    falsePositives: [
      'Lens distortion at short subject distance.',
      'Partial occlusion of the jaw or brow line.',
      'Natural asymmetry between the left and right sides of the face.',
    ],
  },
  EYE_REFLECTION: {
    title: 'Corneal reflection agreement',
    family: 'Physical plausibility',
    slug: '05-signals-tier2.md#corneal',
    falsePositives: [
      'Eyes below roughly 40 pixels, where the reflection is not resolvable.',
      'Glasses, contact lenses, or heavy eye makeup.',
      'Multiple real light sources producing genuinely different highlights.',
      'The subject blinking or squinting at capture time.',
    ],
  },
  CORNEAL_REFLECTION_INCONSISTENT: {
    title: 'Corneal reflection agreement',
    family: 'Physical plausibility',
    slug: '05-signals-tier2.md#corneal',
    falsePositives: [
      'Low eye resolution.',
      'Eyewear reflecting the environment differently per eye.',
      'Asymmetric ambient lighting.',
    ],
  },
  PRNU_SENSOR: {
    title: 'Sensor noise fingerprint',
    family: 'Device forensics',
    slug: '04-signals-tier1.md#prnu',
    falsePositives: [
      'Denoising or night mode, which erases the sensor pattern in a real photo.',
      'Heavy compression before the image reached us.',
      'Cropping away the region the reference fingerprint was built from.',
      'No enrolled reference fingerprint for this device.',
    ],
  },
  SENSOR_NOISE_ABSENT: {
    title: 'Sensor noise fingerprint',
    family: 'Device forensics',
    slug: '04-signals-tier1.md#prnu',
    falsePositives: [
      'Computational photography pipelines that suppress sensor noise.',
      'Recompression stripping high-frequency detail.',
    ],
  },
  TEXTURE_INCONSISTENCY: {
    title: 'Skin texture consistency',
    family: 'Micro-texture',
    slug: '04-signals-tier1.md#texture',
    falsePositives: [
      'Smoothing or "beauty" filters applied by the camera app.',
      'Soft focus, motion blur, or a dirty lens.',
      'Low-light captures where the denoiser has flattened skin detail.',
    ],
  },
  SCREEN_REPLAY_INDICATOR: {
    title: 'Screen replay indicator',
    family: 'Presentation attack',
    slug: '04-signals-tier1.md#replay',
    falsePositives: [
      'A reflective surface behind the subject producing moiré-like patterns.',
      'Striped or finely patterned clothing and backgrounds.',
      'Genuine captures taken in front of a monitor.',
    ],
  },
  MODEL_DISAGREEMENT: {
    title: 'Model disagreement',
    family: 'Uncertainty',
    slug: '07-fusion-uncertainty.md#disagreement',
    falsePositives: [
      'Borderline captures where signals legitimately point in different directions.',
      'One signal operating outside the conditions it was validated for.',
    ],
  },
  METADATA_UNAVAILABLE: {
    title: 'Capture metadata unavailable',
    family: 'Context (never proof)',
    slug: '09-evaluation-governance.md#metadata',
    falsePositives: [
      'Metadata is routinely stripped by messaging apps and web uploads.',
      'Privacy settings that disable EXIF writing on the device.',
      'Absence of metadata is context only and is never evidence of manipulation.',
    ],
  },
};

const FALLBACK: ReasonCodeDoc = {
  title: 'Signal detail',
  family: 'Forensic signal',
  slug: '00-index.md',
  falsePositives: [
    'Compression, resizing, or format conversion between capture and upload.',
    'Lighting and camera hardware outside the range the signal was validated on.',
    'Occlusion or low resolution in the region the signal measures.',
  ],
};

export function reasonCodeDoc(code: string): ReasonCodeDoc {
  return DOCS[code] ?? { ...FALLBACK, title: humanise(code) };
}

export function signalDocsUrl(code: string): string {
  return `${SIGNAL_DOCS_BASE}${reasonCodeDoc(code).slug}`;
}

function humanise(code: string): string {
  return code
    .toLowerCase()
    .split('_')
    .map((word, i) => (i === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ');
}
