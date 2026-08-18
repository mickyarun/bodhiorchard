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

import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

/**
 * Vitest config — dual-environment.
 *
 * Suffix selects the environment, not the subject under test. ``*.test.ts``
 * runs under the lightweight node environment — use it for pure-logic
 * modules. ``*.spec.ts`` runs under jsdom with the @vitejs/plugin-vue
 * pipeline, so SFCs compile and DOM APIs (``mount``, ``getByText``) work.
 * Most ``*.spec.ts`` files are component tests, but any module needing a
 * browser global (``localStorage``, ``File``, ``FormData``) belongs there
 * too — see ``services/api.formdata.spec.ts``.
 *
 * Path alias `@/` is mirrored from vite.config.ts so test imports match
 * production imports.
 *
 * ``jsdom`` is declared in the repo-root ``package.json`` (not just here):
 * vitest resolves ``jsdom`` from the nearest ``node_modules`` ancestor of
 * its own install path, which under npm workspaces is the root. Frontend
 * declares it locally too for IDE type resolution.
 */
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'node',
    globals: false,
    include: ['src/**/*.{test,spec}.ts'],
    environmentMatchGlobs: [
      ['src/**/*.spec.ts', 'jsdom'],
    ],
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
  },
})
