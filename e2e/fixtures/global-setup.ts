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

/**
 * Runs once the stack answers. First it checks the stack is this
 * checkout's (a reused one could belong to another worktree, if ports were
 * moved by hand). Then it loads the app once, so a cold Vite server does
 * its first dependency pass before any test starts.
 */
import { chromium, request } from '@playwright/test'
import { BACKEND_URL, FRONTEND_URL, REPO_ROOT } from '../stack/config.ts'
import { STACK_ORIGINS } from './browser.ts'

async function checkIdentity(): Promise<void> {
  const api = await request.newContext({ baseURL: BACKEND_URL })
  try {
    const response = await api.get('/__e2e/identity')
    const root = response.ok() ? ((await response.json()) as { repoRoot: string }).repoRoot : null
    if (root !== REPO_ROOT) {
      throw new Error(`the stack on ${BACKEND_URL} is not this checkout's (it serves ${root ?? 'no e2e routes'})`)
    }
  } finally {
    await api.dispose()
  }
}

export default async function globalSetup(): Promise<void> {
  await checkIdentity()
  const browser = await chromium.launch()
  try {
    const page = await browser.newPage()
    await page.route((url) => !STACK_ORIGINS.has(url.host), (route) => route.abort())
    await page.goto(`${FRONTEND_URL}/login`)
    // The login page, or the wizard on an empty database.
    await page
      .getByRole('heading', { name: 'Sign in' })
      .or(page.getByRole('heading', { name: 'Welcome to Glideship' }))
      .waitFor({ timeout: 180_000 })
  } finally {
    await browser.close()
  }
}
