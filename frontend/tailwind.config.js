/** @type {import('tailwindcss').Config} */
// CausalGraph design tokens. Values mirror the CSS variables in
// src/styles/cg-tokens.css — change both together.
//
// The interface is monochrome on warm paper; colour is reserved for data
// (ESG domains in the graph) and for status. Serif (Newsreader) is used for
// editorial headlines only; everything functional is set in IBM Plex Sans.
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', '"Helvetica Neue"', 'Arial', '"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei"', 'sans-serif'],
        serif: ['"Newsreader Variable"', 'Newsreader', '"Iowan Old Style"', '"Palatino Linotype"', 'Georgia', '"Songti SC"', 'serif'],
        display: ['"Newsreader Variable"', 'Newsreader', '"Iowan Old Style"', '"Palatino Linotype"', 'Georgia', '"Songti SC"', 'serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', '"SF Mono"', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        paper: {
          DEFAULT: '#FBFAF8',
          sunken: '#F5F3EF',
          hover: '#EFEDE7',
          pressed: '#E8E5DE',
        },
        line: {
          DEFAULT: '#E7E4DD',
          strong: '#D5D1C8',
          soft: '#EFEDE8',
        },
        ink: {
          DEFAULT: '#1A1915',
          2: '#3D3B36',
          3: '#5E5B54',
          4: '#87837A',
          5: '#ABA79E',
          // Older names still referenced in a few places.
          strong: '#000000',
          charcoal: '#2B2A26',
          slate: '#5E5B54',
          steel: '#5E5B54',
          stone: '#87837A',
          muted: '#87837A',
          faint: '#ABA79E',
        },
        canvas: '#FBFAF8',
        surface: {
          DEFAULT: '#FFFFFF',
          soft: '#F5F3EF',
        },
        hairline: {
          DEFAULT: '#E7E4DD',
          soft: '#EFEDE8',
        },
        ok: { DEFAULT: '#2F6F4F', bg: '#E9F2EC', line: '#C9DFD1' },
        warn: { DEFAULT: '#8A5A00', bg: '#FAF1DC', line: '#EBD6A5' },
        err: { DEFAULT: '#B3261E', bg: '#FBECEA', line: '#F0C9C4' },
        info: { DEFAULT: '#2F5AA8', bg: '#EAF0FA', line: '#C9D7F0' },
        success: { DEFAULT: '#2F6F4F', bg: '#E9F2EC' },
        domain: {
          e: '#2F7D5B',
          s: '#3D64C4',
          g: '#B07A1E',
          ai: '#7B5BC0',
          general: '#6F6B63',
        },
      },
      fontSize: {
        '2xs': ['11px', { lineHeight: '16px' }],
        'display-sm': ['28px', { lineHeight: '1.2', letterSpacing: '-0.01em' }],
        'display-md': ['36px', { lineHeight: '1.12', letterSpacing: '-0.015em' }],
        'display-lg': ['48px', { lineHeight: '1.06', letterSpacing: '-0.02em' }],
        'display-xl': ['64px', { lineHeight: '1.02', letterSpacing: '-0.025em' }],
      },
      maxWidth: {
        content: '1200px',
        reading: '680px',
      },
      boxShadow: {
        sm: '0 1px 2px rgba(26, 25, 21, 0.05)',
        md: '0 1px 2px rgba(26, 25, 21, 0.04), 0 4px 16px -2px rgba(26, 25, 21, 0.08)',
        lg: '0 2px 4px rgba(26, 25, 21, 0.04), 0 16px 40px -8px rgba(26, 25, 21, 0.18)',
      },
    },
  },
  plugins: [],
};
