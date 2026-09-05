import { PRIVACY_NOTICE_BODY, PRIVACY_NOTICE_LEAD } from '../lib/copy';

/**
 * §7.1 — persistent, full-width, not dismissible.
 *
 * Rendered as a `contentinfo` landmark so screen-reader users can jump to it,
 * and kept in normal document flow at the bottom of the page rather than
 * fixed, so it can never cover the result it is qualifying.
 */
export function PrivacyNotice() {
  return (
    <footer
      role="contentinfo"
      aria-label="Privacy and limitation notice"
      className="mt-8 border-t border-line bg-sunken"
    >
      <div className="mx-auto max-w-[1400px] px-4 py-4 sm:px-6">
        <p className="text-note text-ink-2">
          <strong className="font-semibold text-ink">{PRIVACY_NOTICE_LEAD}</strong>{' '}
          {PRIVACY_NOTICE_BODY}
        </p>
      </div>
    </footer>
  );
}
