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

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import wasm from 'vite-plugin-wasm'
import topLevelAwait from 'vite-plugin-top-level-await'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
    wasm(),
    topLevelAwait(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
  },
  // Vite's dep optimizer normally crawls only entries reachable from
  // `index.html`. When the user navigates to a route lazy-imported via
  // the router, new Vuetify components surface as "newly optimized
  // dependencies" — and Vite responds with a full page reload. That
  // reload drops any open WebSocket (Colyseus race rooms in particular)
  // mid-handshake, manifesting as "Could not join this race room" the
  // first time a host opens the lobby on a cold dep cache. Expand the
  // crawl to every Vue file under src/ so vite-plugin-vuetify's
  // auto-import resolutions are all discovered at startup and batched
  // into a single optimization pass.
  optimizeDeps: {
    entries: [
      'index.html',
      'src/main.ts',
      'src/views/**/*.vue',
      'src/components/**/*.vue',
      'src/layouts/**/*.vue',
      // Engine Vue overlays render during the race lobby, the exact
      // moment the bug we fixed surfaced. Even though they don't import
      // Vuetify today, including them here means a future <v-card>
      // sneaking in won't silently regress the reload-mid-handshake fix.
      'src/engine/**/*.vue',
    ],
  },
  build: {
    rollupOptions: {
      output: {
        // PlayCanvas is intentionally NOT split into its own manualChunk.
        // A dedicated `playcanvas` chunk surfaced a cross-chunk module-eval
        // race: a minified class identifier inside the playcanvas chunk
        // was undefined at the moment an engine-chunk module called `new`
        // on it, manifesting as "q is not a constructor" at runtime. The
        // failure depends on Rollup version, native-binary platform, and
        // Node major — so Mac and Linux builds can disagree on the same
        // source. Letting Rollup co-locate playcanvas with the engine
        // code that imports it keeps the class definition and its
        // instantiation inside the same module record, removing the race.
        // The engine chunk is still lazy-loaded by the dashboard route,
        // so non-dashboard pages remain unaffected.
        manualChunks(id) {
          if (id.includes('node_modules/@dimforge/rapier3d')) return 'rapier'
          if (id.includes('node_modules/colyseus.js') || id.includes('node_modules/@colyseus')) {
            return 'colyseus'
          }
          // Mermaid has internal circular dependencies between its class
          // constructors. When bundled alongside app code, Rollup's module
          // evaluation order can leave a constructor undefined at the moment
          // another class writes to its .prototype — causing the runtime error
          // "Cannot set properties of undefined (setting 'prototype')".
          // Isolating it into its own chunk ensures Mermaid's module graph is
          // evaluated atomically before any app code references it.
          if (id.includes('node_modules/mermaid') || id.includes('node_modules/@mermaid-js')) {
            return 'mermaid'
          }
          if (id.includes('/src/engine/')) return 'engine'
        },
      },
    },
  },
  server: {
    port: 3000,
    allowedHosts: ['frontendchat.ngrok.app', 'macbook-pro.taile1406f.ts.net'],
    proxy: {
      '/api': {
        // Override the proxy target for side-by-side dev (e.g. a worktree
        // backend on another port) via VITE_API_TARGET. Defaults to :8000.
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        timeout: 300000, // 5 min — AI chat endpoints can be slow
        ws: true,
      },
      // Forward Colyseus through the same origin so HTTPS pages (ngrok,
      // Tailscale Serve) don't hit a mixed-content block when the client
      // tries to reach ws://localhost:2567 directly from an https:// page.
      // `rewrite` strips the /colyseus prefix since the Colyseus server
      // expects /matchmake/... at its root.
      '/colyseus': {
        target: 'http://localhost:2567',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/colyseus/, ''),
      },
    },
  },
})
