import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const HERE = fileURLToPath(new URL(".", import.meta.url));

// In dev the engine runs on :8000 (uvicorn games.crypt_road.app:app); in production it serves this build itself.
const ENGINE = process.env.ENGINE_URL || "http://localhost:8000";
const API = ["/session", "/state", "/allowed", "/act", "/digest", "/reset", "/reload", "/dev", "/health"];
// The manor mystery's API lives under /manor; its page (manor/index.html) is served by Vite itself in dev.
const MANOR_API = ["session", "state", "allowed", "act", "reset", "reload", "dev"].map((p) => `/manor/${p}`);

export default defineConfig({
  base: "./",
  server: {
    proxy: Object.fromEntries([...API, ...MANOR_API].map((p) => [p, { target: ENGINE, changeOrigin: true }])),
    fs: { allow: [".."] }, // fixtures/ lives at the repo root
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Two games, two pages: The Crypt Road at / and the manor mystery at /manor/.
    rollupOptions: { input: { main: resolve(HERE, "index.html"), manor: resolve(HERE, "manor/index.html") } },
  },
});
