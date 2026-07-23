/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#FAF7F1",
        card: "#FFFDF9",
        terminal: "#2B2B2B",
        sqlText: "#7A5230",
        primary: "#5A6E5F",
        accent: "#B88746",
        border: "#E8E0D5",
        darkBg: "#181714",
        darkCard: "#221F19",
        darkBorder: "#37332A",
        darkText: "#EDE7D9",
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["'Inter'", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        // Layered, soft elevation instead of a single hard shadow — this is
        // what makes cards read as "lifted" rather than just bordered.
        soft: "0 1px 2px rgba(43,43,43,0.04), 0 8px 24px -10px rgba(43,43,43,0.10)",
        softHover: "0 2px 4px rgba(43,43,43,0.06), 0 16px 32px -12px rgba(43,43,43,0.16)",
        darkSoft: "0 1px 2px rgba(0,0,0,0.2), 0 8px 24px -10px rgba(0,0,0,0.45)",
        darkSoftHover: "0 2px 4px rgba(0,0,0,0.25), 0 16px 32px -12px rgba(0,0,0,0.55)",
      },
    },
  },
  plugins: [],
};
