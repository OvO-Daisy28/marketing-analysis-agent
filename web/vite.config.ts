import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  base: process.env.VITE_SHOWCASE_ONLY === "true" ? "/marketing-analysis-agent/" : "/",
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
