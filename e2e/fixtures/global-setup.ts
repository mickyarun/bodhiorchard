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
 * Runs once the stack answers:
 *
 * 1. checks each backend is this checkout's (a reused stack could belong to
 *    another worktree, if ports were moved by hand), and notes where its
 *    guard and Vite logs stand, so this run answers only for what follows;
 * 2. creates the main stack's first org before any test can. The login page
 *    signs in to the oldest org, so it has to be fixed before tests seed
 *    orgs in parallel; the login tests add their people to it;
 * 3. loads each frontend once, so a cold Vite server does its first
 *    dependency pass before any test starts.
 */
import { randomBytes } from 'node:crypto'
import { chromium, request } from '@playwright/test'
import { MAIN_STACK, REPO_ROOT, STACKS, type StackTarget } from '../stack/config.ts'
import { stackOrigins } from './browser.ts'
import { saveStartPoint, startRun, viteLogBytes } from './run.ts'
import type { GuardReport } from './types.ts'

async function createLoginOrg(): Promise<void> {
  const api = await request.newContext({ baseURL: MAIN_STACK.backendUrl })
  try {
    // A no-op on a reused stack, whose first org already exists.
    const password = randomBytes(12).toString('base64url')
    const response = await api.post('/__e2e/orgs', { data: { primary: true, members: [], password } })
    if (!response.ok()) throw new Error(`creating the login org failed: ${response.status()} ${await response.text()}`)
  } finally {
    await api.dispose()
  }
}

async function checkAndMark(target: StackTarget): Promise<void> {
  const api = await request.newContext({ baseURL: target.backendUrl })
  try {
    const response = await api.get('/__e2e/identity')
    const root = response.ok() ? ((await response.json()) as { repoRoot: string }).repoRoot : null
    if (root !== REPO_ROOT) {
      throw new Error(`the stack on ${target.backendUrl} is not this checkout's (it serves ${root ?? 'no e2e routes'})`)
    }
    const guard = (await (await api.get('/__e2e/guard', { params: { all: 'true' } })).json()) as GuardReport
    saveStartPoint(target, { ...guard.cursor, viteLogBytes: viteLogBytes(target) })
  } finally {
    await api.dispose()
  }
}

export default async function globalSetup(): Promise<void> {
  startRun()
  await Promise.all(STACKS.map(checkAndMark))
  await createLoginOrg()
  const browser = await chromium.launch()
  try {
    await Promise.all(STACKS.map(async (target) => {
      const page = await browser.newPage()
      const origins = stackOrigins(target)
      await page.route((url) => !origins.has(url.host), (route) => route.abort())
      await page.goto(`${target.frontendUrl}/login`)
      // The login page, or the wizard on an empty database.
      await page
        .getByRole('heading', { name: 'Sign in' })
        .or(page.getByRole('heading', { name: 'Welcome to Glideship' }))
        .waitFor({ timeout: 180_000 })
    }))
  } finally {
    await browser.close()
  }
}
