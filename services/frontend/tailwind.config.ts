import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        circuit: {
          bg: "#0a0e17",
          panel: "#111827",
          border: "#1f2937",
          accent: "#22d3ee",
          green: "#34d399",
          amber: "#fbbf24",
          red: "#f87171",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
