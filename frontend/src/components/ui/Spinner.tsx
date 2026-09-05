interface SpinnerProps {
  label: string;
  size?: number;
}

/**
 * Determinate-looking ring spinner. Under `prefers-reduced-motion` the ring
 * stops rotating (see index.css) and the visible label carries the state.
 */
export function Spinner({ label, size = 16 }: SpinnerProps) {
  return (
    <span className="inline-flex items-center gap-2 text-ink-2">
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="motion-safe:animate-spin"
      >
        <circle
          cx="12"
          cy="12"
          r="9"
          fill="none"
          stroke="var(--border-strong)"
          strokeWidth="3"
        />
        <path
          d="M21 12a9 9 0 0 0-9-9"
          fill="none"
          stroke="var(--blue-500)"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
      <span className="text-[13px]">{label}</span>
    </span>
  );
}
