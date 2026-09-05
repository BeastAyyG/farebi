import type { ConfidenceLevel } from '../types/detection';
import { CONFIDENCE_BADGE } from '../lib/copy';

interface ConfidenceBadgeProps {
  confidence: ConfidenceLevel;
  className?: string;
}

const STYLE: Record<ConfidenceLevel, { chip: string; ink: string; glyph: string }> = {
  low: { chip: 'bg-terracotta-50 border-terracotta-500', ink: 'text-terracotta-700', glyph: '▁' },
  medium: { chip: 'bg-ochre-50 border-ochre-500', ink: 'text-ochre-700', glyph: '▄' },
  high: { chip: 'bg-sage-50 border-sage-500', ink: 'text-sage-700', glyph: '█' },
};

/**
 * §1.3 — confidence badge shown next to the probability sentence.
 * The full sentence is the label; the glyph is a redundant, non-colour cue.
 */
export function ConfidenceBadge({ confidence, className = '' }: ConfidenceBadgeProps) {
  const style = STYLE[confidence];
  return (
    <p
      className={`inline-flex items-start gap-2 rounded-[8px] border px-2.5 py-1.5 text-note ${style.chip} ${style.ink} ${className}`}
    >
      <span aria-hidden="true" className="font-mono leading-5">
        {style.glyph}
      </span>
      <span>{CONFIDENCE_BADGE[confidence]}</span>
    </p>
  );
}
