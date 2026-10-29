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
import { FRONTEND_URL } from './stack/config.ts'

const CI = Boolean(process.env.CI)

export default defineConfig({
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
    baseURL: FRONTEND_URL,
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
    url: FRONTEND_URL,
    reuseExistingServer: !CI,
    timeout: 300_000,
    stdout: 'pipe',
    stderr: 'pipe',
    gracefulShutdown: { signal: 'SIGTERM', timeout: 30_000 },
  },
  projects: [
    // The wizard needs an empty database, so it runs alone, before the rest.
    {
      name: 'setup-wizard',
      testMatch: /setup-wizard\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium',
      testIgnore: /setup-wizard\.spec\.ts/,
      dependencies: ['setup-wizard'],
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
