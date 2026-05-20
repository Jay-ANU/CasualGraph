/** @type {import('tailwindcss').Config} */
// MiniMax-inspired design system.
// Stark black/white canvas + vibrant product-color cards + DM Sans + pill buttons.
// See design/DESIGN.md for the spec.
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // DM Sans is the single typeface across every surface (per spec).
        sans: ['DM Sans', 'Inter', 'Helvetica Neue', 'Helvetica', 'Arial', 'system-ui', 'sans-serif'],
        display: ['DM Sans', 'Inter', 'Helvetica Neue', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'SF Mono', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        // Mono anchor — black + white + neutral steps.
        ink: {
          DEFAULT: '#0a0a0a',
          strong: '#000000',
          charcoal: '#222222',
          slate: '#45515e',
          steel: '#5f5f5f',
          stone: '#8e8e93',
          muted: '#a8aab2',
        },
        canvas: '#ffffff',
        surface: {
          DEFAULT: '#f7f8fa',
          soft: '#f2f3f5',
        },
        hairline: {
          DEFAULT: '#e5e7eb',
          soft: '#eaecf0',
        },
        // Product brand colors — ONLY for product-identity moments.
        brand: {
          coral: '#ff5530',
          magenta: '#ea5ec1',
          blue: '#1456f0',
          'blue-mid': '#3b82f6',
          'blue-deep': '#1d4ed8',
          'blue-700': '#17437d',
          'blue-200': '#bfdbfe',
          cyan: '#3daeff',
          purple: '#a855f7',
        },
        // Domain colors for ESG (E/S/G/AI) — used on product-identity cards & badges.
        domain: {
          e: '#1ba673',       // environmental — verdant green
          'e-bg': '#e8ffea',
          s: '#1456f0',       // social — brand blue
          's-bg': '#dbeafe',
          g: '#ff5530',       // governance — brand coral
          'g-bg': '#fff1ec',
          ai: '#a855f7',      // ai — brand purple
          'ai-bg': '#f5f3ff',
        },
        success: {
          DEFAULT: '#1ba673',
          bg: '#e8ffea',
        },
      },
      fontSize: {
        // MiniMax type ramp.
        'hero': ['80px',     { lineHeight: '1.10', letterSpacing: '0', fontWeight: '600' }],
        'display-lg':['56px',{ lineHeight: '1.10', letterSpacing: '0', fontWeight: '600' }],
        'heading-lg':['40px',{ lineHeight: '1.20', letterSpacing: '0', fontWeight: '600' }],
        'heading-md':['32px',{ lineHeight: '1.25', letterSpacing: '0', fontWeight: '600' }],
        'heading-sm':['24px',{ lineHeight: '1.30', letterSpacing: '0',      fontWeight: '600' }],
        'card-title':['20px',{ lineHeight: '1.40', letterSpacing: '0',      fontWeight: '600' }],
        'subtitle':  ['18px',{ lineHeight: '1.50', letterSpacing: '0',      fontWeight: '500' }],
        'body-md':   ['16px',{ lineHeight: '1.50', letterSpacing: '0',      fontWeight: '400' }],
        'body-sm':   ['14px',{ lineHeight: '1.50', letterSpacing: '0',      fontWeight: '400' }],
        'caption':   ['13px',{ lineHeight: '1.70', letterSpacing: '0',      fontWeight: '400' }],
        'micro':     ['12px',{ lineHeight: '1.50', letterSpacing: '0',      fontWeight: '400' }],
      },
      borderRadius: {
        // Sharp two-tier system: 16px for quiet cards, 32px for vibrant product cards.
        'xs': '4px',
        'sm': '6px',
        'md': '8px',
        'lg': '12px',
        'xl': '16px',
        '2xl': '20px',
        '3xl': '24px',
        'hero': '32px',
        // tailwind's `rounded-full` already gives 9999px.
      },
      spacing: {
        // Section-level spacing tokens.
        'section-sm': '48px',
        'section':    '64px',
        'section-lg': '80px',
        'hero':       '96px',
      },
      maxWidth: {
        // Responsive page-container ramp.
        // `page` = baseline (≤ 1280px screens), `page-wide` = standard desktop,
        // `page-xl` = 2K/4K big-display sweet spot.
        'page':       '1280px',
        'page-wide':  '1440px',
        'page-xl':    '1680px',
        'page-2xl':   '1920px',
      },
      boxShadow: {
        // Flat by default; elevation reserved for sticky/dropdown/modal.
        'subtle':       '0 1px 2px 0 rgba(0, 0, 0, 0.04)',
        'card':         '0 4px 6px 0 rgba(0, 0, 0, 0.08)',
        'atmospheric':  '0 0 22px 0 rgba(0, 0, 0, 0.08)',
        'modal':        '0 12px 16px -4px rgba(36, 36, 36, 0.08)',
      },
      animation: {
        'fade-in':   'fadeIn 0.5s ease-in-out',
        'slide-up':  'slideUp 0.5s ease-out',
        'pulse-slow':'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn:  { '0%': { opacity: '0' },                                  '100%': { opacity: '1' } },
        slideUp: { '0%': { transform: 'translateY(20px)', opacity: '0' },   '100%': { transform: 'translateY(0)', opacity: '1' } },
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
