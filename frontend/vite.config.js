import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/ai": { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/auth": { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/notes": { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/memories": { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/files": { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/settings": { target: "http://127.0.0.1:5000", changeOrigin: true },
    },
  },
});
