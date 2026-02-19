/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        agent: {
          elliot: '#60a5fa',
          trader: '#4ade80',
          dev: '#c084fc',
        },
      },
    },
  },
  plugins: [],
};
