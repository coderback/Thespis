import { defineConfig } from "vite";

// In dev the engine runs on :8000 (uvicorn games.crypt_road.app:app); in production it serves this build itself.
const ENGINE = process.env.ENGINE_URL || "http://localhost:8000";
const API = ["/session", "/state", "/allowed", "/act", "/digest", "/reset", "/reload", "/dev", "/health"];

export default defineConfig({
  base: "./",
  server: {
    proxy: Object.fromEntries(API.map((p) => [p, { target: ENGINE, changeOrigin: true }])),
    fs: { allow: [".."] }, // fixtures/ lives at the repo root
  },
  build: { outDir: "dist", emptyOutDir: true },
});
