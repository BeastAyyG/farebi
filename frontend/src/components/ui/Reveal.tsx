import type { CSSProperties, ReactNode } from 'react';
import { STAGGER_MS } from '../../lib/motion';

type RevealKind = 'rise' | 'pop' | 'slide' | 'fade';

interface RevealProps {
  children: ReactNode;
  /** Position in the sequence; multiplied by the stagger step. */
  index?: number;
  kind?: RevealKind;
  /** Explicit delay in ms, overriding `index`. */
  delay?: number;
  className?: string;
  style?: CSSProperties;
}

const CLASS: Record<RevealKind, string> = {
  rise: 'a-rise',
  pop: 'a-pop',
  slide: 'a-slide-in',
  fade: 'a-fade',
};

/**
 * Entrance wrapper. Purely presentational — it adds a CSS animation class and
 * a `--delay` custom property, so a whole column can cascade in without any
 * JS timers, and the reduced-motion block switches it all off at once.
 */
export function Reveal({
  children,
  index = 0,
  kind = 'rise',
  delay,
  className = '',
  style,
}: RevealProps) {
  const ms = delay ?? index * STAGGER_MS;
  return (
    <div
      className={`${CLASS[kind]} ${className}`}
      style={{ ...style, ['--delay' as string]: `${ms}ms` }}
    >
      {children}
    </div>
  );
}
