import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Vite config for the Matchbook frontend.
//
// The dev server proxies /api to the FastAPI container so that the
// frontend can be run standalone (`npm run dev`) against a running
// backend without cross-origin concerns. In production the frontend
// is served by Nginx and /api is proxied by Apache on the host — same
// shape, different proxy.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3086',
        changeOrigin: true,
      },
    },
  },
});
