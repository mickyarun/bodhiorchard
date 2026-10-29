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

import { defineConfig, devices } from '@playwright/test'
import type { StackTarget } from './stack/config.ts'
import { MAIN_STACK, WIZARD_STACK } from './stack/config.ts'

const CI = Boolean(process.env.CI)

export default defineConfig<{ stackTarget: StackTarget }>({
  testDir: './specs',
  outputDir: './test-results',
  fullyParallel: true,
  forbidOnly: CI,
  // No retries: a flaky test is a bug to fix, not to hide.
  retries: 0,
  workers: CI ? 2 : undefined,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: CI
    ? [['github'], ['list'], ['html', { open: 'never' }]]
    : [['list'], ['html', { open: 'never' }]],
  globalSetup: './fixtures/global-setup.ts',
  globalTeardown: './fixtures/global-teardown.ts',
  use: {
    baseURL: MAIN_STACK.frontendUrl,
    stackTarget: MAIN_STACK,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  // The whole stack: Docker Postgres and Redis, the fake-backed backend,
  // multiplayer and Vite, on ports of its own. Locally a running
  // `npm run stack` is reused; CI always starts a fresh one.
  webServer: {
    command: 'node stack/run.ts',
    url: MAIN_STACK.frontendUrl,
    reuseExistingServer: !CI,
    timeout: 300_000,
    stdout: 'pipe',
    stderr: 'pipe',
    gracefulShutdown: { signal: 'SIGTERM', timeout: 30_000 },
  },
  projects: [
    // The wizard needs an empty database, so it has a backend of its own and
    // never makes another spec wait.
    {
      name: 'setup-wizard',
      testMatch: /setup-wizard\.spec\.ts/,
      // One database: repeats (--repeat-each, burn-in) must not run side by side.
      workers: 1,
      use: { ...devices['Desktop Chrome'], baseURL: WIZARD_STACK.frontendUrl, stackTarget: WIZARD_STACK },
    },
    {
      name: 'chromium',
      testIgnore: /setup-wizard\.spec\.ts/,
      grepInvert: /@mobile/,
      use: { ...devices['Desktop Chrome'] },
    },
    // Screens that change below the tablet breakpoint, on a phone-sized touch device.
    {
      name: 'mobile',
      grep: /@mobile/,
      use: { ...devices['Pixel 7'] },
    },
  ],
})
