import type { Config } from 'tailwindcss';

/**
 * Tailwind is a thin mapping layer over `src/styles/tokens.css`.
 * No literal colour may appear here — every value is a CSS custom property,
 * which is what lets `DESIGN.md` claim a single source of truth.
 */
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-translucent': 'var(--surface-translucent)',
        sunken: 'var(--surface-sunken)',
        line: 'var(--border)',
        'line-strong': 'var(--border-strong)',
        ink: 'var(--text)',
        'ink-2': 'var(--text-2)',
        'ink-3': 'var(--text-3)',
        focus: 'var(--focus)',

        blue: {
          50: 'var(--blue-50)',
          100: 'var(--blue-100)',
          200: 'var(--blue-200)',
          300: 'var(--blue-300)',
          500: 'var(--blue-500)',
          600: 'var(--blue-600)',
          700: 'var(--blue-700)',
        },
        sky: {
          50: 'var(--sky-50)',
          100: 'var(--sky-100)',
          200: 'var(--sky-200)',
          500: 'var(--sky-500)',
          600: 'var(--sky-600)',
        },
        aqua: {
          50: 'var(--aqua-50)',
          100: 'var(--aqua-100)',
          300: 'var(--aqua-300)',
          500: 'var(--aqua-500)',
        },
        terracotta: {
          50: 'var(--terracotta-50)',
          100: 'var(--terracotta-100)',
          500: 'var(--terracotta-500)',
          700: 'var(--terracotta-700)',
        },
        ochre: {
          50: 'var(--ochre-50)',
          100: 'var(--ochre-100)',
          500: 'var(--ochre-500)',
          700: 'var(--ochre-700)',
        },
        sage: {
          50: 'var(--sage-50)',
          100: 'var(--sage-100)',
          500: 'var(--sage-500)',
          700: 'var(--sage-700)',
        },

        verdict: {
          'real-anchor': 'var(--v-real-anchor)',
          'real-fill': 'var(--v-real-fill)',
          'real-ink': 'var(--v-real-ink)',
          'real-border': 'var(--v-real-border)',
          'fake-anchor': 'var(--v-fake-anchor)',
          'fake-fill': 'var(--v-fake-fill)',
          'fake-ink': 'var(--v-fake-ink)',
          'fake-border': 'var(--v-fake-border)',
          'unc-anchor': 'var(--v-unc-anchor)',
          'unc-fill': 'var(--v-unc-fill)',
          'unc-ink': 'var(--v-unc-ink)',
          'unc-border': 'var(--v-unc-border)',
          'na-anchor': 'var(--v-na-anchor)',
          'na-fill': 'var(--v-na-fill)',
          'na-ink': 'var(--v-na-ink)',
          'na-border': 'var(--v-na-border)',
        },
      },
      borderRadius: {
        card: 'var(--radius-card)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        micro: ['12px', { lineHeight: '1.5' }],
        note: ['13px', { lineHeight: '1.55' }],
        base: ['15px', { lineHeight: '1.55' }],
      },
      transitionTimingFunction: {
        out: 'var(--ease)',
      },
      transitionDuration: {
        motion: 'var(--motion)',
      },
      backgroundImage: {
        attribution:
          'linear-gradient(90deg, var(--heat-real-2) 0%, var(--heat-real-1) 22%, var(--heat-mid) 50%, var(--heat-fake-1) 72%, var(--heat-fake-2) 88%, var(--heat-fake-3) 100%)',
      },
    },
  },
  plugins: [],
};

export default config;
