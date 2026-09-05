import { formatBytes, type ValidationSuccess } from '../lib/validateImage';

interface ImagePreviewProps {
  previewUrl: string;
  meta: ValidationSuccess | null;
  filename: string;
  onClear: () => void;
  disabled?: boolean;
}

/**
 * §2.3 — a downscaled preview (max 400×400) shown immediately after the file
 * passes local validation, alongside the facts the reviewer needs to trust
 * that the right file was picked.
 */
export function ImagePreview({
  previewUrl,
  meta,
  filename,
  onClear,
  disabled = false,
}: ImagePreviewProps) {
  return (
    <section aria-labelledby="preview-heading" className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <h2 id="preview-heading" className="text-[15px] font-semibold text-ink">
          Preview
        </h2>
        <button type="button" className="btn-quiet" onClick={onClear} disabled={disabled}>
          Clear
        </button>
      </div>

      <div className="mt-3 flex justify-center rounded-[10px] border border-line bg-sunken p-3">
        <img
          src={previewUrl}
          alt={`Downscaled preview of the uploaded capture ${filename}`}
          className="max-h-[400px] max-w-full rounded-[8px] object-contain"
        />
      </div>

      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-note">
        <dt className="text-ink-3">File</dt>
        <dd className="truncate font-mono text-ink-2" title={filename}>
          {filename}
        </dd>
        {meta ? (
          <>
            <dt className="text-ink-3">Format</dt>
            <dd className="font-mono uppercase text-ink-2">{meta.format}</dd>
            <dt className="text-ink-3">Dimensions</dt>
            <dd className="font-mono text-ink-2">
              {meta.width}×{meta.height}
            </dd>
            <dt className="text-ink-3">Size</dt>
            <dd className="font-mono text-ink-2">{formatBytes(meta.bytes)}</dd>
          </>
        ) : null}
      </dl>

      <p className="limitation mt-3">
        The preview is a compressed copy rendered in your browser. The detector receives the
        original file.
      </p>
    </section>
  );
}
