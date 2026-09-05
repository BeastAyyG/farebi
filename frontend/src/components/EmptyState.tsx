import { EMPTY_STATE_HINT, EMPTY_STATE_TITLE } from '../lib/copy';
import { EmptyIllustration } from './ui/Icon';
import { Spinner } from './ui/Spinner';

interface EmptyStateProps {
  /** Renders the in-flight variant instead of the idle one. */
  loading?: boolean;
}

/** §9.3 — placeholder shown when nothing has been uploaded, or while scoring. */
export function EmptyState({ loading = false }: EmptyStateProps) {
  return (
    <section
      aria-labelledby="empty-heading"
      className="card flex min-h-[340px] flex-col items-center justify-center gap-4 p-8 text-center"
    >
      <EmptyIllustration />

      {loading ? (
        <>
          <h2 id="empty-heading" className="text-[16px] font-semibold text-ink">
            Analysing capture
          </h2>
          <Spinner label="Running signals and fusion…" />
          <p className="limitation max-w-sm">
            This usually takes a few seconds. The image is deleted after inference by default.
          </p>
        </>
      ) : (
        <>
          <h2 id="empty-heading" className="text-[16px] font-semibold text-ink">
            {EMPTY_STATE_TITLE}
          </h2>
          <p className="text-note text-ink-2">{EMPTY_STATE_HINT}</p>
          <p className="limitation max-w-sm">
            This tool estimates image manipulation only. It is one input to a review, never the
            decision itself.
          </p>
        </>
      )}
    </section>
  );
}
