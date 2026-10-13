import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    // The pipeline is Python, so /api goes to the FastAPI server. In production
    // that same server serves this bundle, so the app always uses relative paths.
    // SHORTS_API points a second dev server at another API (e.g. a stub
    // server on :8001 beside the real one on :8000).
    proxy: { "/api": { target: (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.SHORTS_API ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
