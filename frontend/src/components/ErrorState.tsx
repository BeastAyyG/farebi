import type { RefObject } from 'react';
import type { DetectError } from '../types/detection';
import { PER_RESULT_WARNING } from '../lib/copy';

interface ErrorStateProps {
  error: DetectError;
  onRetry?: () => void;
  /** Set by App so focus lands here when the error replaces a result. */
  headingRef?: RefObject<HTMLHeadingElement | null>;
}

const KIND_LABEL: Record<DetectError['kind'], string> = {
  validation: 'Upload rejected',
  http_400: 'Request rejected',
  http_500: 'Server error',
  timeout: 'Request timed out',
  network: 'Connection problem',
};

/**
 * §9.1 / §9.2 — every failure path. The message is passed through verbatim
 * from the client, which has already resolved it to the exact spec string (or,
 * for a 400, to the API's own `detail`).
 */
export function ErrorState({ error, onRetry, headingRef }: ErrorStateProps) {
  const retryable = error.kind !== 'validation';

  return (
    <section
      role="alert"
      aria-labelledby="error-heading"
      className="rounded-card border border-terracotta-500 bg-terracotta-50 p-4"
    >
      <div className="flex items-start gap-2.5">
        <span aria-hidden="true" className="mt-0.5 font-mono text-terracotta-700">
          ✕
        </span>
        <div className="min-w-0 flex-1">
          <h2
            id="error-heading"
            ref={headingRef}
            tabIndex={-1}
            className="text-[15px] font-semibold text-terracotta-700"
          >
            {KIND_LABEL[error.kind]}
            {error.status ? (
              <span className="ml-2 font-mono text-micro font-normal opacity-80">
                HTTP {error.status}
              </span>
            ) : null}
          </h2>

          <p className="mt-1 text-note text-terracotta-700">{error.message}</p>

          {retryable && onRetry ? (
            <button type="button" onClick={onRetry} className="btn-secondary mt-3">
              Try again
            </button>
          ) : null}

          <p className="limitation mt-3">{PER_RESULT_WARNING}</p>
        </div>
      </div>
    </section>
  );
}
