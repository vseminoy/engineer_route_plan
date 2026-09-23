import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Backend base prefix is /api/v1 (05_spec_backend.md §4) — the dev proxy
// forwards the whole /api tree so the app can call it with relative paths.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': '/src'
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_ORIGIN ?? 'http://localhost:8001',
        changeOrigin: true
      }
    }
  }
});
