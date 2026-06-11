// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Separate Vite config for the public-facing landing site at bodhiorchard.ai.
// Builds a multi-page, pre-rendered (vite-ssg) static site — one HTML file per
// route in landing-src/router.ts.
//
// Project root for this build: frontend/landing-src/
//   (keeps it isolated from the main app's index.html / src/main.ts,
//    which otherwise get pulled in and drag the entire engine + wasm
//    dependency chain along with them.)
//
// Entry:  landing-src/index.html → main.ts → LandingLayout.vue → pages/*.vue
// Output: frontend/dist-landing/  (+ sitemap.xml, generated in onFinished)
// Deploy: npx wrangler pages deploy frontend/dist-landing
import { writeFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { LANDING_ROUTES } from './landing-src/routes-manifest'

const SITE_ORIGIN = 'https://bodhiorchard.ai'

function buildSitemap(): string {
  const lastmod = new Date().toISOString().slice(0, 10)
  const urls = LANDING_ROUTES.map((r) => {
    const loc = r.path === '/' ? `${SITE_ORIGIN}/` : `${SITE_ORIGIN}${r.path}`
    return [
      '  <url>',
      `    <loc>${loc}</loc>`,
      `    <lastmod>${lastmod}</lastmod>`,
      '    <changefreq>monthly</changefreq>',
      `    <priority>${r.priority.toFixed(1)}</priority>`,
      '  </url>',
    ].join('\n')
  }).join('\n')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`
}

export default defineConfig({
  root: fileURLToPath(new URL('./landing-src', import.meta.url)),
  // publicDir resolves relative to root → landing-src/public/
  // (contains only what the landing site needs; the main app's public/ has
  // ~70MB of 3D assets that must NOT be uploaded to Cloudflare Pages.)
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
  },
  build: {
    outDir: fileURLToPath(new URL('./dist-landing', import.meta.url)),
    emptyOutDir: true,
  },
  // Vuetify imports per-component CSS files (e.g. VChip.css) directly. Node's
  // ESM loader can't import .css without help, so bundle Vuetify into the SSR
  // output instead of leaving it externalised.
  ssr: {
    noExternal: ['vuetify'],
  },
  // vite-ssg extends UserConfig; the field is untyped, hence the directive.
  // @ts-expect-error vite-ssg extension
  ssgOptions: {
    formatting: 'minify',
    script: 'async',
    crittersOptions: false,
    // Clean URLs: each route emits <route>/index.html (e.g. /methodology/).
    dirStyle: 'nested',
    // Drop the catch-all (and any future dynamic route) from the crawl — it
    // can't be statically enumerated. The 6 static routes each pre-render.
    includedRoutes(paths: string[]): string[] {
      return paths.filter((p) => !p.includes(':') && !p.includes('*'))
    },
    // Emit sitemap.xml from the canonical route manifest after all pages render.
    onFinished(): void {
      const out = fileURLToPath(new URL('./dist-landing/sitemap.xml', import.meta.url))
      writeFileSync(out, buildSitemap())
    },
  },
})
