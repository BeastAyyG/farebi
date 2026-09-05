import { useId, useState, type ReactNode } from 'react';

interface DisclosureProps {
  summary: string;
  /** Small right-aligned hint, e.g. "illustrative only". */
  hint?: string;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
}

/**
 * Collapsed-by-default section used for the two §11 extras, which must stay
 * visually quiet and never compete with the verdict.
 */
export function Disclosure({
  summary,
  hint,
  defaultOpen = false,
  children,
  className = '',
}: DisclosureProps) {
  const id = useId();
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`rounded-[10px] border border-line bg-surface ${className}`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={`${id}-content`}
        onClick={() => setOpen((prev) => !prev)}
        className="anim flex w-full items-center justify-between gap-3 rounded-[10px] px-3.5 py-2.5 text-left transition-colors hover:bg-sunken"
      >
        <span className="flex items-center gap-2 text-[14px] font-medium text-ink-2">
          <span aria-hidden="true" className="font-mono text-ink-3">
            {open ? '−' : '+'}
          </span>
          {summary}
        </span>
        {hint ? <span className="text-micro text-ink-3">{hint}</span> : null}
      </button>

      {open ? (
        <div id={`${id}-content`} className="border-t border-line px-3.5 py-3.5">
          {children}
        </div>
      ) : (
        <div id={`${id}-content`} hidden />
      )}
    </div>
  );
}
