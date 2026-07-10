/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// nc-web build + test config. The test block runs Vitest in a jsdom env with globals, so the pure
// logic modules (MatrixService over a mocked sdk, parsers, decoders) are unit-tested without a homeserver.
export default defineConfig({
  plugins: [react()],
  build: {
    // Split the heavy matrix-js-sdk into its own long-cached vendor chunk (it changes far less often
    // than app code), so returning users only re-download the small app bundle on each deploy.
    chunkSizeWarningLimit: 12000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined; // app code stays in the entry chunk
          if (id.includes("matrix-js-sdk") || id.includes("@matrix-org")) return "matrix-sdk";
          if (id.includes("/react") || id.includes("/react-dom") || id.includes("/scheduler")) return "react";
          return "vendor";
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
