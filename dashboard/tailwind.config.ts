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
        primary: "var(--primary)",
        "primary-foreground": "var(--primary-foreground)",
        secondary: "var(--secondary)",
        "secondary-foreground": "var(--secondary-foreground)",
        destructive: "var(--destructive)",
        "destructive-foreground": "var(--destructive-foreground)",
        success: "var(--success)",
        "success-foreground": "var(--success-foreground)",
        border: "var(--border)",
        card: "var(--card)",
        "card-foreground": "var(--card-foreground)",
        muted: "var(--muted)",
        "muted-foreground": "var(--muted-foreground)",
        // Named design system colors
        terracotta: "var(--terracotta)",
        "warm-charcoal": "var(--warm-charcoal)",
        "warm-gray": "var(--warm-gray)",
        "amber-gold": "var(--amber-gold)",
        "sage-green": "var(--sage-green)",
        "soft-cream": "var(--soft-cream)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
export default config;
