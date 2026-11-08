
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png', 'favicon-16.png', 'favicon-32.png'],
      manifest: {
        name: 'Waymark — Travel Intelligence',
        short_name: 'Waymark',
        description:
          'Plan journeys with live routing, weather, hazard alerts, and nearby facilities.',
        theme_color: '#203C5A',
        background_color: '#F7F8FA',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          {
            src: '/icon-maskable-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'maskable',
          },
          {
            src: '/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // Default glob only covers the build output; this is the app
        // shell precache for offline startup.
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        runtimeCaching: [
          {
            // Matches the backend API regardless of its origin (dev vs
            // deployed, same-origin or not) since url.pathname is
            // origin-independent. NetworkFirst: journey/weather/alert
            // data should always prefer live data over cache, but a
            // recent response is better than nothing when offline or on
            // a flaky connection. GET-only by default, so this never
            // caches POST/DELETE (journey analysis, saved-journey
            // writes) — exactly the endpoints that must never be served
            // stale or replayed from cache.
            urlPattern: ({ url }) => url.pathname.startsWith('/api/v1/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'waymark-api',
              networkTimeoutSeconds: 8,
              expiration: { maxEntries: 100, maxAgeSeconds: 5 * 60 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // OSM map tiles: CacheFirst so a previously-viewed area's
            // tiles still render offline or on a flaky connection — the
            // single biggest win for a travel app used on the move.
            urlPattern: ({ url }) => url.hostname === 'tile.openstreetmap.org',
            handler: 'CacheFirst',
            options: {
              cacheName: 'waymark-map-tiles',
              expiration: { maxEntries: 500, maxAgeSeconds: 7 * 24 * 60 * 60 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
      devOptions: {
        // Service worker is disabled in `npm run dev` by default; this
        // whole feature is build/preview-only, which is the right scope
        // for this change (dev keeps its normal fast-refresh behavior).
        enabled: false,
      },
    }),
  ],
})
