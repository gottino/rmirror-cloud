import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        // Main palette - blue/greyish tones
        'primary-darkest': '#22223B',  // Deep navy
        'primary-dark': '#4A4E69',     // Slate blue
        'primary-light': '#9A8C98',    // Mauve grey
        'primary-lighter': '#C9ADA7',  // Rose grey
        'primary-lightest': '#F2E9E4', // Warm white
        // Status lights - subdued streetlight palette
        'status-error': '#8B4049',     // Subdued red
        'status-warning': '#9B7E46',   // Subdued amber/yellow
        'status-success': '#5B7961',   // Subdued green
      },
    },
  },
  plugins: [],
};
export default config;
