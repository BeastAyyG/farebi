import type { Config } from "tailwindcss";

export default {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--bg)",
        surface: "var(--surface)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        text: "var(--text)",
        "text-2": "var(--text-2)",
        "text-3": "var(--text-3)",
        focus: "var(--focus)",
        terracotta: {
          500: "#D97757",
          700: "#B45F44",
          100: "#F7E7E1",
        },
        ochre: {
          500: "#E0AD6B",
          700: "#A57A48",
          100: "#FFF8F0",
        },
        sage: {
          500: "#88A795",
          700": "#6B8975",
          100: "#F7FAF9",
        },
        blue: {
          500: "#3368A0",
        },
        sky: {
          500: "#66A3BF",
        },
        aqua: {
          500: "#C8DFDB",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;