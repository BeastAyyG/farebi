import { useEffect, useRef, useState } from 'react';
import type { DetectResponse, Verdict } from '../types/detection';
import { MANUAL_REVIEW, formatProbability } from '../lib/copy';
import { VERDICT_STYLE } from '../lib/verdict';

/** What the human concluded, independent of the model. */
export type ManualDecision = 'genuine' | 'manipulated' | 'escalate';

export interface ManualReviewPanelProps {
  result: DetectResponse;
  decision: ManualDecision | null;
  note: string;
  onDecide: (decision: ManualDecision | null) => void;
  onNoteChange: (note: string) => void;
  /** Announced through the app's live region. */
  onAnnounce?: (message: string) => void;
}

interface DecisionStyle {
  label: string;
  hint: string;
  glyph: string;
  fill: string;
  ink: string;
  border: string;
  stripe: string;
}

const DECISION_STYLE: Record<ManualDecision, DecisionStyle> = {
  genuine: {
    label: MANUAL_REVIEW.real,
    hint: MANUAL_REVIEW.realHint,
    glyph: '✓',
    fill: 'bg-verdict-real-fill',
    ink: 'text-verdict-real-ink',
    border: 'border-verdict-real-border',
    stripe: 'bg-verdict-real-anchor',
  },
  manipulated: {
    label: MANUAL_REVIEW.fake,
    hint: MANUAL_REVIEW.fakeHint,
    glyph: '✕',
    fill: 'bg-verdict-fake-fill',
    ink: 'text-verdict-fake-ink',
    border: 'border-verdict-fake-border',
    stripe: 'bg-verdict-fake-anchor',
  },
  escalate: {
    label: MANUAL_REVIEW.escalate,
    hint: MANUAL_REVIEW.escalateHint,
    glyph: '↑',
    fill: 'bg-verdict-unc-fill',
    ink: 'text-verdict-unc-ink',
    border: 'border-verdict-unc-border',
    stripe: 'bg-verdict-unc-anchor',
  },
};

/**
 * Which manual decision the model's verdict would correspond to, so we can
 * tell the reviewer whether they are agreeing or overriding.
 *
 * `uncertain` and `unable_to_assess` map to nothing: the detector explicitly
 * declined, so there is no position to contradict.
 */
function modelPosition(verdict: Verdict): ManualDecision | null {
  if (verdict === 'likely_real') return 'genuine';
  if (verdict === 'likely_fake') return 'manipulated';
  return null;
}

/**
 * The human decision point.
 *
 * Farebi's whole premise is that it is a risk signal and never an autonomous
 * rejection engine, which only means something if there is somewhere for the
 * human judgement to actually land. This is that place.
 *
 * Two deliberate frictions:
 *  - Overriding the detector requires a written reason. Disagreements are the
 *    most valuable events this system produces and an unexplained one is
 *    worthless later.
 *  - The recorded outcome always names the reviewer as its author and carries
 *    both version strings, so it can never be mistaken for a model output.
 */
export function ManualReviewPanel({
  result,
  decision,
  note,
  onDecide,
  onNoteChange,
  onAnnounce,
}: ManualReviewPanelProps) {
  const [copied, setCopied] = useState(false);
  const [showNoteError, setShowNoteError] = useState(false);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const outcomeRef = useRef<HTMLParagraphElement>(null);

  const modelSays = modelPosition(result.verdict);
  const isOverride = decision !== null && modelSays !== null && decision !== modelSays;
  const noteMissing = isOverride && note.trim().length === 0;

  useEffect(() => setCopied(false), [decision, note]);

  function choose(next: ManualDecision) {
    const cleared = decision === next;
    onDecide(cleared ? null : next);
    setShowNoteError(false);

    if (cleared) {
      onAnnounce?.('Decision cleared.');
      return;
    }

    const style = DECISION_STYLE[next];
    const overriding = modelSays !== null && next !== modelSays;
    onAnnounce?.(
      `Decision recorded: ${style.label}. ${
        overriding ? MANUAL_REVIEW.overrides : modelSays === null ? '' : MANUAL_REVIEW.agrees
      }`.trim(),
    );
    if (overriding) {
      // Pull the reviewer straight into the justification they now owe.
      requestAnimationFrame(() => noteRef.current?.focus());
    }
  }

  function buildRecord(): string {
    const style = decision ? DECISION_STYLE[decision] : null;
    const lines = [
      'FAREBI REVIEW RECORD',
      `request_id:          ${result.request_id}`,
      `reviewed_at:         ${new Date().toISOString()}`,
      '',
      'DETECTOR OUTPUT (estimate)',
      `verdict:             ${VERDICT_STYLE[result.verdict].label}`,
      result.verdict === 'unable_to_assess'
        ? 'fake_probability:    not reported'
        : `fake_probability:    ${formatProbability(result.fake_probability)}`,
      `confidence_level:    ${result.confidence_level}`,
      `uncertainty_score:   ${formatProbability(result.uncertainty_score)}`,
      `model_version:       ${result.model_version}`,
      `threshold_version:   ${result.threshold_version ?? 'not reported'}`,
      `calibration_version: ${result.calibration_version ?? 'not reported'}`,
      '',
      'REVIEWER DECISION (authoritative)',
      `decision:            ${style ? style.label : 'none recorded'}`,
      `relation_to_model:   ${
        decision === null
          ? 'n/a'
          : modelSays === null
            ? 'detector declined to decide'
            : isOverride
              ? 'OVERRIDES detector'
              : 'agrees with detector'
      }`,
      `reason:              ${note.trim() || '(none given)'}`,
      '',
      'This detector analyzes image manipulation only. It does not verify',
      'liveness, identity ownership, or document authenticity. The reviewer',
      'decision above is the authoritative outcome for this request.',
    ];
    return lines.join('\n');
  }

  async function copyRecord() {
    if (noteMissing) {
      setShowNoteError(true);
      noteRef.current?.focus();
      return;
    }
    const text = buildRecord();
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      onAnnounce?.('Decision record copied to the clipboard.');
    } catch {
      // Clipboard can be blocked by permissions; fall back to a selectable
      // textarea rather than silently failing.
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand('copy');
        setCopied(true);
        onAnnounce?.('Decision record copied to the clipboard.');
      } catch {
        onAnnounce?.('Could not copy automatically. Select the record manually.');
      }
      area.remove();
    }
  }

  const chosen = decision ? DECISION_STYLE[decision] : null;

  return (
    <section aria-labelledby="manual-review-heading" className="card overflow-hidden">
      <div className={`h-1.5 w-full ${chosen ? chosen.stripe : 'bg-line-strong'}`} aria-hidden="true" />

      <div className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="manual-review-heading" className="text-[15px] font-semibold text-ink">
            {MANUAL_REVIEW.heading}
          </h2>
          {!chosen ? (
            <span className="rounded-[6px] border border-line-strong bg-sunken px-2 py-0.5 text-micro font-medium text-ink-2">
              {MANUAL_REVIEW.pending}
            </span>
          ) : null}
        </div>

        <p className="mt-1 text-note text-ink-2">{MANUAL_REVIEW.intro}</p>

        {/* The three choices. Radio semantics: exactly one outcome per request. */}
        <div
          role="radiogroup"
          aria-label={MANUAL_REVIEW.heading}
          className="mt-4 grid gap-2 sm:grid-cols-3"
        >
          {(Object.keys(DECISION_STYLE) as ManualDecision[]).map((key) => {
            const style = DECISION_STYLE[key];
            const active = decision === key;
            return (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => choose(key)}
                className={[
                  'a-press flex flex-col items-start gap-1 rounded-[10px] border px-3 py-2.5 text-left',
                  active
                    ? `${style.fill} ${style.ink} ${style.border} shadow-card`
                    : 'border-line bg-surface text-ink-2 hover:border-line-strong hover:bg-sunken',
                ].join(' ')}
              >
                <span className="flex items-center gap-2 text-[14px] font-semibold">
                  <span
                    aria-hidden="true"
                    className={[
                      'inline-flex h-5 w-5 items-center justify-center rounded-full border font-mono text-[11px]',
                      active ? `${style.border} bg-surface` : 'border-line-strong',
                    ].join(' ')}
                  >
                    {active ? style.glyph : ''}
                  </span>
                  {style.label}
                </span>
                <span className="text-micro leading-snug opacity-90">{style.hint}</span>
              </button>
            );
          })}
        </div>

        {chosen ? (
          <div className="a-rise mt-4">
            {/* Agreement / override, stated plainly. */}
            <p
              ref={outcomeRef}
              className={[
                'flex items-start gap-2 rounded-[8px] border px-3 py-2 text-note',
                isOverride
                  ? 'border-ochre-500 bg-ochre-50 text-ochre-700'
                  : 'border-line bg-sunken text-ink-2',
              ].join(' ')}
            >
              <span aria-hidden="true" className="mt-px font-mono">
                {isOverride ? '⚠' : 'ℹ'}
              </span>
              <span>
                {modelSays === null
                  ? MANUAL_REVIEW.noModelView
                  : isOverride
                    ? MANUAL_REVIEW.overrides
                    : MANUAL_REVIEW.agrees}{' '}
                <span className="text-ink-3">
                  Detector said {VERDICT_STYLE[result.verdict].label}
                  {result.verdict !== 'unable_to_assess'
                    ? ` at ${formatProbability(result.fake_probability)}`
                    : ''}
                  .
                </span>
              </span>
            </p>

            <div className="mt-3">
              <label htmlFor="review-note" className="flex items-baseline justify-between">
                <span className="text-note font-medium text-ink-2">
                  {MANUAL_REVIEW.noteLabel}
                  {isOverride ? (
                    <span className="ml-1 text-terracotta-700" aria-hidden="true">
                      *
                    </span>
                  ) : (
                    <span className="ml-1 text-ink-3">(optional)</span>
                  )}
                </span>
                <span className="font-mono text-micro text-ink-3">{note.trim().length}/280</span>
              </label>
              <textarea
                ref={noteRef}
                id="review-note"
                rows={2}
                maxLength={280}
                value={note}
                required={isOverride}
                aria-required={isOverride}
                aria-invalid={showNoteError && noteMissing}
                aria-describedby={showNoteError && noteMissing ? 'review-note-error' : undefined}
                placeholder={MANUAL_REVIEW.notePlaceholder}
                onChange={(event) => {
                  onNoteChange(event.target.value);
                  if (event.target.value.trim()) setShowNoteError(false);
                }}
                className={[
                  'anim mt-1.5 w-full resize-y rounded-[8px] border bg-surface px-3 py-2 text-note text-ink',
                  'placeholder:text-ink-3',
                  showNoteError && noteMissing ? 'border-terracotta-500' : 'border-line-strong',
                ].join(' ')}
              />
              {showNoteError && noteMissing ? (
                <p id="review-note-error" role="alert" className="mt-1 text-note text-terracotta-700">
                  {MANUAL_REVIEW.noteRequired}
                </p>
              ) : isOverride ? (
                <p className="limitation mt-1">{MANUAL_REVIEW.noteRequired}</p>
              ) : null}
            </div>

            {/* The authoritative outcome, stated as a human judgement. */}
            <div
              className={`mt-3 flex flex-wrap items-center gap-3 rounded-[8px] border px-3 py-2.5 ${chosen.fill} ${chosen.border}`}
            >
              <span
                className={`inline-flex items-center gap-2 text-[15px] font-semibold ${chosen.ink}`}
              >
                <span aria-hidden="true" className="font-mono">
                  {chosen.glyph}
                </span>
                {MANUAL_REVIEW.recorded}: {chosen.label}
              </span>
              <span className="ml-auto flex gap-2">
                <button type="button" className="btn-secondary" onClick={() => choose(decision!)}>
                  {MANUAL_REVIEW.change}
                </button>
                <button type="button" className="btn-primary" onClick={copyRecord}>
                  {copied ? MANUAL_REVIEW.copied : MANUAL_REVIEW.copy}
                </button>
              </span>
            </div>
          </div>
        ) : null}

        <p className="limitation mt-3">{MANUAL_REVIEW.disclaimer}</p>
      </div>
    </section>
  );
}
