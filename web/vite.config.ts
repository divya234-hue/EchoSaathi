import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // host: true so your phone can reach the dev server over the LAN
    host: true,
    port: 5173,
    proxy: {
      "/ws": { target: "ws://localhost:8080", ws: true },
      "/api": "http://localhost:8080",
    },
  },
  build: { outDir: "dist" },
});
