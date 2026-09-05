import { useId, useState, type ReactNode } from 'react';

interface TooltipProps {
  /** The trigger. Must be focusable content — rendered inside a button. */
  children: ReactNode;
  /** Tooltip body. */
  content: ReactNode;
  /** Accessible name for the trigger button. */
  triggerLabel: string;
  align?: 'left' | 'right';
  className?: string;
}

/**
 * Hover- and keyboard-operable tooltip.
 *
 * The content is always in the DOM and referenced via `aria-describedby`, so
 * screen readers get it whether or not the visual popover is open, and Escape
 * dismisses it for sighted keyboard users.
 */
export function Tooltip({
  children,
  content,
  triggerLabel,
  align = 'left',
  className = '',
}: TooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <span
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={triggerLabel}
        aria-describedby={`${id}-tip`}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setOpen(false);
        }}
        className="anim inline-flex items-center gap-1 rounded-[6px] text-left transition-colors"
      >
        {children}
      </button>

      <span
        role="tooltip"
        id={`${id}-tip`}
        className={[
          'anim pointer-events-none absolute top-full z-30 mt-2 w-72 rounded-card border border-line',
          'bg-surface p-3 text-note text-ink-2 shadow-card',
          align === 'right' ? 'right-0' : 'left-0',
          open ? 'visible opacity-100' : 'invisible opacity-0',
        ].join(' ')}
      >
        {content}
      </span>
    </span>
  );
}
