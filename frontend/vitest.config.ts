// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineConfig } from 'vitest/config'
import { fileURLToPath, URL } from 'node:url'

/**
 * Vitest config — minimal setup for utility/unit tests.
 *
 * Uses the Node environment (no jsdom) because the existing tests target
 * pure-logic modules like SerializedExecutor that don't touch the DOM.
 * Vue component tests would need `environment: 'jsdom'` and the @vitejs/plugin-vue
 * pipeline — those can be added later if needed.
 *
 * Path alias `@/` is mirrored from vite.config.ts so test imports match
 * production imports.
 */
export default defineConfig({
  test: {
    environment: 'node',
    globals: false,
    include: ['src/**/*.{test,spec}.ts'],
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
