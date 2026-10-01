import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The production build is emitted into the Python package so `adversi serve`
// can ship the UI without a separate web server.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/adversi/server/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", ws: true },
    },
  },
});
