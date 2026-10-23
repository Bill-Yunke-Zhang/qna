import type { Config } from 'tailwindcss';

// Colors are the semantic tokens in src/index.css (T8), and nothing else:
// `colors` replaces Tailwind's palette instead of extending it, so a raw
// utility like `bg-slate-800` doesn't exist here and can't creep back in.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      inherit: 'inherit',
      canvas: token('canvas'),
      surface: {
        DEFAULT: token('surface'),
        raised: token('surface-raised'),
        hover: token('surface-hover'),
      },
      line: { DEFAULT: token('line'), strong: token('line-strong') },
      ink: {
        DEFAULT: token('ink'),
        secondary: token('ink-secondary'),
        muted: token('ink-muted'),
        subtle: token('ink-subtle'),
      },
      accent: {
        DEFAULT: token('accent'),
        hover: token('accent-hover'),
        soft: token('accent-soft'),
        ink: token('accent-ink'),
      },
      'on-accent': token('on-accent'),
      danger: {
        DEFAULT: token('danger'),
        hover: token('danger-hover'),
        soft: token('danger-soft'),
        ink: token('danger-ink'),
      },
      success: { DEFAULT: token('success'), soft: token('success-soft'), ink: token('success-ink') },
      warning: { DEFAULT: token('warning'), soft: token('warning-soft'), ink: token('warning-ink') },
      ai: { soft: token('ai-soft'), ink: token('ai-ink') },
      focus: token('focus'),
    },
    extend: {
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
      },
      boxShadow: {
        card: 'var(--shadow-card)',
      },
    },
  },
  plugins: [],
} satisfies Config;
