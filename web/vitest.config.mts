import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  // tsconfig's `jsx: "preserve"` leaves JSX for Next's compiler; tests need it compiled.
  oxc: { jsx: { runtime: "automatic" } },
  test: {
    // The slices persist the session in localStorage.
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    setupFiles: ["src/test/setup.ts"],
    // Pins the gateway origin api.ts reads at import, whatever the shell exports.
    env: { NEXT_PUBLIC_GATEWAY_URL: "http://gateway.test" },
    unstubEnvs: true,
  },
});
