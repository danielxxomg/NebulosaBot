import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  plugins: [],
  theme: {
    extend: {
      borderRadius: {
        lg: "var(--radius)",
        md: "var(--radius-md)",
        sm: "var(--radius-sm)",
        xl: "var(--radius-xl)",
        xs: "var(--radius-xs)",
      },
      colors: {
        accent: "var(--color-accent)",
        "accent-foreground": "var(--color-accent-foreground)",
        background: "var(--color-background)",
        border: "var(--color-border)",
        card: "var(--color-card)",
        "card-foreground": "var(--color-card-foreground)",
        destructive: "var(--color-destructive)",
        foreground: "var(--color-foreground)",
        input: "var(--color-input)",
        muted: "var(--color-muted)",
        "muted-foreground": "var(--color-muted-foreground)",
        primary: "var(--color-primary)",
        "primary-foreground": "var(--color-primary-foreground)",
        ring: "var(--color-ring)",
        secondary: "var(--color-secondary)",
        "secondary-foreground": "var(--color-secondary-foreground)",
      },
    },
  },
};

export default config;
