import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api requests to the backend so the frontend can use relative URLs.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
