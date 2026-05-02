import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'node:path';

// Vite config for the Matchbook frontend.
//
// The dev server proxies /api to the FastAPI container so that the
// frontend can be run standalone (`npm run dev`) against a running
// backend without cross-origin concerns. In production the frontend
// is served by Nginx and /api is proxied by Apache on the host — same
// shape, different proxy.
//
// VitePWA: emits manifest.webmanifest + a minimal service worker so the
// app is installable on Android/Chrome. Online-only — `navigateFallback:
// null` disables the offline app-shell, and we don't precache /api
// responses, so the SW is effectively just an installability shim.
// `registerType: 'autoUpdate'` means a returning user picks up the new
// build silently on next navigation after a deploy.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      includeAssets: ['icons/icon.svg'],
      workbox: {
        navigateFallback: null,
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
      },
      manifest: {
        name: 'Matchbook',
        short_name: 'Matchbook',
        description: 'CV ↔ job matching',
        theme_color: '#b84a28',
        background_color: '#f7f3ee',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
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
