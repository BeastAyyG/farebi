/**
 * Motion helpers.
 *
 * The rule these encode: bars, markers and shapes may animate, but the
 * numbers a reviewer reads are correct on the very first painted frame. We
 * never count a probability up from zero — a half-rendered "0.31" that is
 * actually 0.64 is a misread waiting to happen.
 */

import { useEffect, useState } from 'react';

/**
 * Returns 0 on the first paint, then the target value, so a CSS width
 * transition animates the bar in. Server rendering and reduced-motion users
 * get the final value immediately.
 */
export function useGrow(target: number, enabled = true): number {
  const [value, setValue] = useState(() => (enabled && !prefersReducedMotion() ? 0 : target));

  useEffect(() => {
    if (!enabled || prefersReducedMotion()) {
      setValue(target);
      return;
    }
    // Two frames: one to commit the 0 state, one to trigger the transition.
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setValue(target));
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, [enabled, target]);

  return value;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Stagger step, in ms, for sequential reveals. */
export const STAGGER_MS = 55;
