// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineConfig } from 'vitest/config'

/**
 * Vitest config for the multiplayer Colyseus server.
 *
 * Node environment (no DOM) — server-side sim tests don't touch browser APIs.
 * Matches the frontend's minimal vitest setup pattern (see frontend/vitest.config.ts).
 */
export default defineConfig({
  test: {
    environment: 'node',
    globals: false,
    include: ['src/**/*.{test,spec}.ts'],
  },
})
