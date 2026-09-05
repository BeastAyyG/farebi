/**
 * Minimal PNG chunk surgery so the downloaded heatmap carries its limitation
 * notice with it (§4.3). A heatmap that escapes the UI without its caveat is
 * exactly the failure mode the spec is guarding against.
 *
 * We insert `tEXt` chunks immediately after IHDR. No re-encoding, no canvas —
 * the pixel data is byte-identical to what the model produced.
 */

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

let crcTable: Uint32Array | null = null;

function getCrcTable(): Uint32Array {
  if (crcTable) return crcTable;
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  crcTable = table;
  return table;
}

function crc32(bytes: Uint8Array): number {
  const table = getCrcTable();
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) {
    c = table[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

/** PNG tEXt keywords are Latin-1, 1–79 chars. Values are Latin-1 too. */
function toLatin1(input: string): Uint8Array {
  const normalised = input
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/[\u2013\u2014]/g, '-')
    .replace(/\u2026/g, '...');
  const out = new Uint8Array(normalised.length);
  for (let i = 0; i < normalised.length; i += 1) {
    const code = normalised.charCodeAt(i);
    out[i] = code < 256 ? code : 0x3f; // '?'
  }
  return out;
}

function buildTextChunk(keyword: string, value: string): Uint8Array {
  const key = toLatin1(keyword.slice(0, 79));
  const val = toLatin1(value);
  const dataLength = key.length + 1 + val.length;

  const chunk = new Uint8Array(12 + dataLength);
  const view = new DataView(chunk.buffer);

  view.setUint32(0, dataLength);
  chunk.set(toLatin1('tEXt'), 4);
  chunk.set(key, 8);
  chunk[8 + key.length] = 0x00;
  chunk.set(val, 9 + key.length);

  const crc = crc32(chunk.subarray(4, 8 + dataLength));
  view.setUint32(8 + dataLength, crc);
  return chunk;
}

export function base64ToBytes(base64: string): Uint8Array {
  const clean = base64.replace(/^data:image\/\w+;base64,/, '').replace(/\s/g, '');
  const binary = atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function isPng(bytes: Uint8Array): boolean {
  return PNG_SIGNATURE.every((b, i) => bytes[i] === b);
}

/**
 * Returns a new PNG byte array with the supplied metadata inserted after IHDR.
 * If the input is not a PNG the bytes are returned untouched.
 */
export function withPngTextMetadata(
  bytes: Uint8Array,
  metadata: Record<string, string>,
): Uint8Array {
  if (!isPng(bytes) || bytes.length < 8 + 25) return bytes;

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const ihdrLength = view.getUint32(8);
  const insertAt = 8 + 12 + ihdrLength; // signature + IHDR chunk

  const chunks = Object.entries(metadata).map(([k, v]) => buildTextChunk(k, v));
  const extra = chunks.reduce((sum, c) => sum + c.length, 0);

  const out = new Uint8Array(bytes.length + extra);
  out.set(bytes.subarray(0, insertAt), 0);
  let offset = insertAt;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  out.set(bytes.subarray(insertAt), offset);
  return out;
}

export function downloadBytes(bytes: Uint8Array, filename: string, mime = 'image/png'): void {
  const copy = new Uint8Array(bytes); // detach from any pooled buffer
  const blob = new Blob([copy], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Give the browser a tick to start the download before revoking.
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
