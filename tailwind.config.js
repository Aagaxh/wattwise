/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          950: '#060911',
          900: '#0a0f1d',
          850: '#0f172a',
          800: '#141e38',
          700: '#1e293b',
          600: '#334155',
        },
        cyan: {
          400: '#22d3ee',
          500: '#06b6d4',
          electric: '#00f2fe',
        },
        purple: {
          500: '#a855f7',
          600: '#9333ea',
          electric: '#7928ca',
        }
      },
      boxShadow: {
        'glow-cyan': '0 0 25px -5px rgba(6, 182, 212, 0.35)',
        'glow-purple': '0 0 25px -5px rgba(168, 85, 247, 0.35)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
      },
      backdropBlur: {
        'xs': '2px',
      }
    },
  },
  plugins: [],
}
