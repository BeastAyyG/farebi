/**
 * Small inline SVG glyphs. Each is `aria-hidden` by default: every icon in
 * this UI sits next to a text label, because §10 forbids conveying state by
 * icon or colour alone.
 */

interface IconProps {
  size?: number;
  className?: string;
}

export function UploadIcon({ size = 20, className = '' }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </svg>
  );
}

export function DownloadIcon({ size = 16, className = '' }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="M12 4v12" />
      <path d="m7 11 5 5 5-5" />
      <path d="M4 20h16" />
    </svg>
  );
}

export function InfoIcon({ size = 15, className = '' }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      aria-hidden="true"
      className={className}
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 7.6h.01" />
    </svg>
  );
}

/**
 * Placeholder illustration for the empty state (§9.3): a framed portrait
 * crop with a dashed scan line, drawn from palette tokens only.
 */
export function EmptyIllustration({ className = '' }: IconProps) {
  return (
    <svg
      viewBox="0 0 160 120"
      width="160"
      height="120"
      role="img"
      aria-label="Placeholder illustration of an empty image frame awaiting an upload"
      className={className}
    >
      <rect
        x="12"
        y="10"
        width="136"
        height="100"
        rx="10"
        fill="var(--surface-sunken)"
        stroke="var(--border-strong)"
        strokeWidth="1.5"
      />
      <circle cx="80" cy="52" r="20" fill="var(--aqua-100)" stroke="var(--aqua-300)" strokeWidth="1.5" />
      <path
        d="M52 96c4-15 14-22 28-22s24 7 28 22"
        fill="var(--sky-100)"
        stroke="var(--sky-200)"
        strokeWidth="1.5"
      />
      <path
        d="M20 84h120"
        stroke="var(--blue-300)"
        strokeWidth="1.5"
        strokeDasharray="5 5"
        opacity="0.8"
      />
      <rect x="12" y="10" width="136" height="100" rx="10" fill="none" stroke="var(--border)" />
    </svg>
  );
}
