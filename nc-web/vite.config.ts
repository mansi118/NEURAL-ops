/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// nc-web build + test config. The test block runs Vitest in a jsdom env with globals, so the pure
// logic modules (MatrixService over a mocked sdk, parsers, decoders) are unit-tested without a homeserver.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
