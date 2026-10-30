import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#ffffff",
        canvas: "#f7f8fa",
        ink: "#172033",
        muted: "#5f6b7a",
        primary: "#2563eb",
      },
      boxShadow: {
        panel: "0 1px 2px rgb(15 23 42 / 0.05), 0 1px 3px rgb(15 23 42 / 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
