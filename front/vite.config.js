var _a;
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
                target: (_a = process.env.VITE_BACKEND_ORIGIN) !== null && _a !== void 0 ? _a : 'http://localhost:8000',
                changeOrigin: true
            }
        }
    }
});
