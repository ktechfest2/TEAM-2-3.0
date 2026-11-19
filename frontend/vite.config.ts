/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const INDEXED_PATHS = ['/', '/polling-units', '/results', '/verification', '/updates', '/incidents', '/report-incident', '/phone-access']

/** Writes robots.txt, plus sitemap.xml when VITE_SITE_URL gives the public origin. */
function seoFiles(siteUrl: string | undefined): Plugin {
  const origin = siteUrl?.replace(/\/+$/, '')
  return {
    name: 'verivote-seo-files',
    apply: 'build',
    generateBundle() {
      const robots = ['User-agent: *', 'Disallow: /admin', 'Disallow: /account', 'Disallow: /evidence', 'Allow: /']
      if (origin) {
        robots.push('', `Sitemap: ${origin}/sitemap.xml`)
        const urls = INDEXED_PATHS.map((path) => `  <url><loc>${origin}${path}</loc></url>`).join('\n')
        this.emitFile({
          type: 'asset',
          fileName: 'sitemap.xml',
          source: `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
        })
      }
      this.emitFile({ type: 'asset', fileName: 'robots.txt', source: `${robots.join('\n')}\n` })
    },
    transformIndexHtml(html) {
      if (!origin) return html
      const image = `${origin}/images/feature-status.jpg`
      return html
        .replaceAll('content="/images/feature-status.jpg"', `content="${image}"`)
        .replace('"name": "VoteTrace",', `"name": "VoteTrace",\n        "url": "${origin}/",`)
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [
    seoFiles(loadEnv(mode, process.cwd(), 'VITE_').VITE_SITE_URL || undefined),
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'VoteTrace',
        short_name: 'VoteTrace',
        description: 'Every Vote, Every Voice. Offline-first electoral evidence and result verification.',
        theme_color: '#011b33',
        background_color: '#ffffff',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: '/maskable-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,woff2,geojson}'],
        navigateFallback: '/index.html',
        // API responses and private evidence must never be served from the SW cache.
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [],
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  preview: { port: 4173, strictPort: true },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    testTimeout: 20_000,
    hookTimeout: 20_000,
  },
}))
