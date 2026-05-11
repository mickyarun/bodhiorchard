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
  build: {
    rollupOptions: {
      output: {
        // Split heavy 3rd-party + engine code into stable chunks so:
        //  - dashboard route doesn't ship 1.5MB of PlayCanvas as one bundle
        //  - engine edits don't invalidate the playcanvas chunk hash
        //  - browser parallelises the network fetches
        manualChunks(id) {
          if (id.includes('node_modules/playcanvas')) return 'playcanvas'
          if (id.includes('node_modules/@dimforge/rapier3d')) return 'rapier'
          if (id.includes('node_modules/colyseus.js') || id.includes('node_modules/@colyseus')) {
            return 'colyseus'
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
        target: 'http://localhost:8000',
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
