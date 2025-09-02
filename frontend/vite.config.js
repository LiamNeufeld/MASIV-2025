import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Keep this simple to avoid ??/|| mixing.
// Set VITE_API_PROXY in your shell if you want to point the dev proxy elsewhere.
const PROXY_TARGET = process.env.VITE_API_PROXY || "http://localhost:5001";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: PROXY_TARGET,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
