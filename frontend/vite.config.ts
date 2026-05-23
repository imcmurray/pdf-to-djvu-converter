import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api requests to the backend so the frontend can use relative URLs.
export default defineConfig(({ mode }) => {
  // `'.'` resolves to the vite project root (this directory). No @types/node needed.
  const env = loadEnv(mode, ".", "VITE_");
  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      proxy: {
        "/api": {
          target: env.VITE_API_BASE || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
