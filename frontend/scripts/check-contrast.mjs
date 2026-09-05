#!/usr/bin/env node
/**
 * Contrast audit for the token pairs actually used by the UI.
 *
 * frebi.md §10 requires >= 4.5:1 for all text. This script parses
 * `src/styles/tokens.css` — so it can never drift from the real values — and
 * fails if any declared text/background pair falls below the floor.
 *
 *   npm run check:contrast
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const cssPath = resolve(here, '../src/styles/tokens.css');

const css = readFileSync(cssPath, 'utf8');
const tokens = new Map();
for (const [, name, value] of css.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
  tokens.set(name, value);
}

const AA = 4.5;

/** Every pair where text of colour A is rendered on background B. */
const PAIRS = [
  ['text', 'bg', 'body text on the page'],
  ['text', 'surface', 'body text on a card'],
  ['text', 'surface-sunken', 'body text on a sunken panel'],
  ['text-2', 'surface', 'secondary text on a card'],
  ['text-2', 'bg', 'secondary text on the page'],
  ['text-2', 'surface-sunken', 'secondary text on a sunken panel'],
  ['text-3', 'surface', 'limitation text on a card'],
  ['text-3', 'bg', 'limitation text on the page'],
  ['text-3', 'surface-sunken', 'limitation text on a sunken panel'],
  ['blue-600', 'surface', 'link on a card'],
  ['blue-600', 'bg', 'link on the page'],
  ['blue-700', 'blue-50', 'signal code tag on hover'],
  ['surface', 'blue-500', 'primary button label'],
  ['surface', 'blue-600', 'primary button label on hover'],
  ['v-real-ink', 'v-real-fill', 'Likely Real verdict card'],
  ['v-fake-ink', 'v-fake-fill', 'Likely Fake verdict card'],
  ['v-unc-ink', 'v-unc-fill', 'Uncertain verdict card'],
  ['v-na-ink', 'v-na-fill', 'Unable to Assess verdict card'],
  ['ochre-700', 'ochre-50', 'uncertainty banner and warnings'],
  ['ochre-700', 'ochre-100', 'warning text on the amber band zone'],
  ['terracotta-700', 'terracotta-50', 'error state'],
  ['terracotta-700', 'terracotta-100', 'error text on the red band zone'],
  ['sage-700', 'sage-50', 'quality pass chip'],
  ['sage-700', 'sage-100', 'quality text on the green band zone'],
];

function channel(value) {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex) {
  const n = hex.replace('#', '');
  const r = Number.parseInt(n.slice(0, 2), 16);
  const g = Number.parseInt(n.slice(2, 4), 16);
  const b = Number.parseInt(n.slice(4, 6), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

let failures = 0;
console.log(`Contrast audit - floor ${AA.toFixed(1)}:1 (frebi.md section 10)\n`);

for (const [fg, bg, label] of PAIRS) {
  const fgHex = tokens.get(fg);
  const bgHex = tokens.get(bg);
  if (!fgHex || !bgHex) {
    console.error(`  MISSING  --${fg} / --${bg}`);
    failures += 1;
    continue;
  }
  const ratio = contrast(fgHex, bgHex);
  const ok = ratio >= AA;
  if (!ok) failures += 1;
  console.log(
    `  ${ratio.toFixed(2).padStart(5)}  ${ok ? 'pass' : 'FAIL'}  ${label}  (--${fg} on --${bg})`,
  );
}

console.log();
if (failures > 0) {
  console.error(`${failures} pair(s) below ${AA}:1.`);
  process.exit(1);
}
console.log(`All ${PAIRS.length} pairs meet ${AA}:1.`);
