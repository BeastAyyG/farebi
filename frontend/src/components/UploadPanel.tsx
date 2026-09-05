import { useCallback, useId, useRef, useState, type DragEvent, type ChangeEvent } from 'react';
import { EMPTY_STATE_HINT, VALIDATING_LABEL } from '../lib/copy';
import {
  MAX_PIXEL_DIM,
  MAX_UPLOAD_BYTES,
  formatBytes,
  validateImageFile,
  type ValidationSuccess,
} from '../lib/validateImage';
import { Spinner } from './ui/Spinner';
import { UploadIcon } from './ui/Icon';

export interface UploadPanelProps {
  /** Fires with the validated file, ready to POST. */
  onSelect: (file: File, meta: ValidationSuccess) => void;
  /** Fires with a preview object URL as soon as one exists (§2.3). */
  onPreview: (previewUrl: string | null) => void;
  /** Fires with the exact §9.1 string when pre-validation rejects the file. */
  onError: (message: string) => void;
  /** Disables interaction while a request is in flight. */
  busy?: boolean;
}

type PanelState = 'idle' | 'validating';

/**
 * Browse + drag-and-drop, with client-side pre-validation before anything
 * leaves the browser. This is a convenience gate, not a security control —
 * the API re-checks everything.
 */
export function UploadPanel({ onSelect, onPreview, onError, busy = false }: UploadPanelProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<PanelState>('idle');
  const [dragging, setDragging] = useState(false);

  const handleFile = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      setState('validating');
      onPreview(null);

      const result = await validateImageFile(file);
      setState('idle');

      if (!result.ok) {
        onError(result.message);
        return;
      }
      onPreview(result.previewUrl);
      onSelect(file, result);
    },
    [onError, onPreview, onSelect],
  );

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    void handleFile(event.target.files?.[0]);
    // Allow re-selecting the same file after an error.
    event.target.value = '';
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (busy || state === 'validating') return;
    void handleFile(event.dataTransfer.files?.[0]);
  }

  const disabled = busy || state === 'validating';

  return (
    <section aria-labelledby={`${inputId}-heading`} className="card p-4">
      <h2 id={`${inputId}-heading`} className="text-[15px] font-semibold text-ink">
        Upload capture
      </h2>
      <p className="mt-1 text-note text-ink-2">
        {EMPTY_STATE_HINT}. Maximum {MAX_PIXEL_DIM}×{MAX_PIXEL_DIM} pixels.
      </p>

      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={[
          'anim mt-3 flex flex-col items-center justify-center gap-3 rounded-card border border-dashed px-4 py-8 text-center transition-colors',
          dragging ? 'border-blue-500 bg-blue-50' : 'border-line-strong bg-sunken',
          disabled ? 'opacity-70' : '',
        ].join(' ')}
      >
        <UploadIcon size={26} className="text-blue-500" />

        {state === 'validating' ? (
          <Spinner label={VALIDATING_LABEL} />
        ) : (
          <>
            <p className="text-[14px] text-ink-2">
              Drag an image here, or choose a file from your device.
            </p>
            {/* The input is visually hidden but still focusable; the label
                carries the focus ring via focus-within so keyboard users see
                a normal button. */}
            <label
              htmlFor={inputId}
              className="btn-primary cursor-pointer focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--focus)]"
            >
              Choose image
              <input
                ref={inputRef}
                id={inputId}
                type="file"
                accept="image/jpeg,image/png"
                onChange={onInputChange}
                disabled={disabled}
                className="sr-only"
              />
            </label>
            <p className="limitation">
              JPEG or PNG, up to {formatBytes(MAX_UPLOAD_BYTES)}. Checked locally before upload.
            </p>
          </>
        )}
      </div>

      <p className="limitation mt-3">
        The uploaded image is sent once to the detector and deleted after inference by default.
      </p>
    </section>
  );
}
