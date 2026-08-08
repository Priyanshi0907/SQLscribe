import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Without this file, Vite has no way to know it should run .jsx files
// through @vitejs/plugin-react — it falls back to esbuild's default
// "classic" JSX transform, which compiles <Foo /> to React.createElement(Foo)
// and expects a global `React` to already be in scope. Since none of this
// project's components import React by name (only named hooks like
// useState), that reference is always undefined at runtime — hence
// "Uncaught ReferenceError: React is not defined". The react() plugin
// switches Vite to the modern automatic JSX runtime, which imports what
// it needs per-file and needs no global React at all.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
    globals: true,
  },
});
