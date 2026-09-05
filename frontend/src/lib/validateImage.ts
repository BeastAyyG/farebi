/**
 * Client-side pre-validation. This is a courtesy check that saves a round trip
 * and gives an immediate, specific reason — it is NOT a security boundary.
 * `src/farebi/core/security.py` remains authoritative.
 *
 * Checks, in order:
 *   1. size <= 10MB
 *   2. real magic bytes (never the MIME type or the filename)
 *   3. single frame (no APNG, no animated GIF smuggled as .png)
 *   4. decoded dimensions <= 2048x2048
 */

import { UPLOAD_ERROR, UPLOAD_ERROR_DIMENSIONS } from './copy';

export const JPEG_MAGIC = [0xff, 0xd8, 0xff];
export const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

export const MAX_UPLOAD_BYTES = readInt(import.meta.env.VITE_MAX_UPLOAD_BYTES, 10 * 1024 * 1024);
export const MAX_PIXEL_DIM = readInt(import.meta.env.VITE_MAX_PIXEL_DIM, 2048);
/** Preview is downscaled to fit this box (§2.3). */
export const PREVIEW_MAX_EDGE = 400;

function readInt(raw: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(raw ?? '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export type DetectedFormat = 'jpeg' | 'png';

export interface ValidationSuccess {
  ok: true;
  format: DetectedFormat;
  width: number;
  height: number;
  /** Object URL of a downscaled preview; caller must revoke it. */
  previewUrl: string;
  bytes: number;
}

export interface ValidationFailure {
  ok: false;
  /** Already the exact §9.1 string. */
  message: string;
}

export type ValidationResult = ValidationSuccess | ValidationFailure;

function startsWith(bytes: Uint8Array, magic: number[]): boolean {
  if (bytes.length < magic.length) return false;
  return magic.every((b, i) => bytes[i] === b);
}

export function sniffFormat(bytes: Uint8Array): DetectedFormat | null {
  if (startsWith(bytes, PNG_MAGIC)) return 'png';
  if (startsWith(bytes, JPEG_MAGIC)) return 'jpeg';
  return null;
}

/**
 * APNG detection: an `acTL` chunk appearing before the first `IDAT` marks the
 * file as animated, which the API rejects as multi-frame.
 */
export function isAnimatedPng(bytes: Uint8Array): boolean {
  const limit = Math.min(bytes.length, 1024 * 256);
  for (let i = 8; i + 4 <= limit; i += 1) {
    const tag = String.fromCharCode(bytes[i], bytes[i + 1], bytes[i + 2], bytes[i + 3]);
    if (tag === 'acTL') return true;
    if (tag === 'IDAT') return false;
  }
  return false;
}

/** GIF/TIFF smuggled under a .png or .jpg name. */
export function isKnownMultiFrameContainer(bytes: Uint8Array): boolean {
  const gif = [0x47, 0x49, 0x46, 0x38]; // "GIF8"
  const tiffLe = [0x49, 0x49, 0x2a, 0x00];
  const tiffBe = [0x4d, 0x4d, 0x00, 0x2a];
  return startsWith(bytes, gif) || startsWith(bytes, tiffLe) || startsWith(bytes, tiffBe);
}

async function decodeDimensions(file: File): Promise<{ width: number; height: number } | null> {
  // createImageBitmap throws on corrupt/truncated data, which is exactly the
  // signal we want for the "corrupt file" branch.
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file);
      const dims = { width: bitmap.width, height: bitmap.height };
      bitmap.close?.();
      return dims;
    } catch {
      return null;
    }
  }
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
      URL.revokeObjectURL(url);
    };
    img.onerror = () => {
      resolve(null);
      URL.revokeObjectURL(url);
    };
    img.src = url;
  });
}

/** Downscale to <= 400x400 for the preview pane; falls back to the raw blob. */
async function buildPreview(file: File, width: number, height: number): Promise<string> {
  const scale = Math.min(1, PREVIEW_MAX_EDGE / Math.max(width, height));
  if (scale >= 1 || typeof document === 'undefined') {
    return URL.createObjectURL(file);
  }
  try {
    const bitmap = await createImageBitmap(file);
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const ctx = canvas.getContext('2d');
    if (!ctx) return URL.createObjectURL(file);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', 0.85),
    );
    return blob ? URL.createObjectURL(blob) : URL.createObjectURL(file);
  } catch {
    return URL.createObjectURL(file);
  }
}

export async function validateImageFile(file: File): Promise<ValidationResult> {
  if (file.size > MAX_UPLOAD_BYTES) {
    return { ok: false, message: UPLOAD_ERROR.tooLarge };
  }
  if (file.size === 0) {
    return { ok: false, message: UPLOAD_ERROR.corrupt };
  }

  let head: Uint8Array;
  try {
    head = new Uint8Array(await file.slice(0, 1024 * 256).arrayBuffer());
  } catch {
    return { ok: false, message: UPLOAD_ERROR.corrupt };
  }

  if (isKnownMultiFrameContainer(head)) {
    return { ok: false, message: UPLOAD_ERROR.multiFrame };
  }

  const format = sniffFormat(head);
  if (!format) {
    return { ok: false, message: UPLOAD_ERROR.invalidFormat };
  }

  if (format === 'png' && isAnimatedPng(head)) {
    return { ok: false, message: UPLOAD_ERROR.multiFrame };
  }

  const dims = await decodeDimensions(file);
  if (!dims || dims.width === 0 || dims.height === 0) {
    return { ok: false, message: UPLOAD_ERROR.corrupt };
  }
  if (dims.width > MAX_PIXEL_DIM || dims.height > MAX_PIXEL_DIM) {
    return { ok: false, message: UPLOAD_ERROR_DIMENSIONS };
  }

  const previewUrl = await buildPreview(file, dims.width, dims.height);
  return {
    ok: true,
    format,
    width: dims.width,
    height: dims.height,
    previewUrl,
    bytes: file.size,
  };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
