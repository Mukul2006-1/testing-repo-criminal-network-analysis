/** ARGUS "Sovereign Intelligence" tokens from the Stitch design system:
 *  light surfaces, indigo primary (#3525cd / #4f46e5), Inter + JetBrains Mono.
 *
 * @type {import('tailwindcss').Config}
 */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        argus: {
          50: "#eef0ff",
          100: "#e2dfff",
          200: "#c3c0ff",
          300: "#a5a0fb",
          400: "#7c74f5",
          500: "#4f46e5",
          600: "#4338ca",
          700: "#3525cd",
          800: "#3323cc",
          900: "#1e1b4b",
          950: "#0f172a",
        },
        surface: "#f8f9ff",
        ink: "#0b1c30",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(15, 23, 42, 0.06), 0 1px 2px -1px rgba(15, 23, 42, 0.04)",
      },
    },
  },
  plugins: [],
};
