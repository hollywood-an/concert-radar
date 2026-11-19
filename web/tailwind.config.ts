import type { Config } from "tailwindcss";

// The palette is a risograph gig flyer: two bright inks and one dark one on cool paper.
// Pink is for actions. Highlighter marks what is the user's own: followed artists and
// new matches. Everything else is ink on paper.
const config: Config = {
  content: [
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "#F2F1F6",
        sheet: "#FFFFFF",
        ink: { DEFAULT: "#1B1A4B", soft: "#5A587E", faint: "#8D8BAA" },
        line: "#DAD8E8",
        stub: "#E9E7F5",
        pink: { DEFAULT: "#E3126B", deep: "#B80D56", wash: "#FDE7F0" },
        highlighter: { DEFAULT: "#FFE04A", deep: "#F2CC0C" },
      },
      fontFamily: {
        sans: ["var(--font-body)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "Impact", "Haettenschweiler", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
