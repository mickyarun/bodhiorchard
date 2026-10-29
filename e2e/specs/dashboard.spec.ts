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
 * Smoke checks for the dashboard. The 3D garden is checked only for loading
 * cleanly: its rendering is the engine's own business, not a browser flow.
 */
import type { Page } from '@playwright/test'
import { seedOrg } from '../fixtures/stack.ts'
import { expect, test } from '../fixtures/test.ts'

/**
 * Resolves once the page's live room has sent it something: the
 * multiplayer socket (through the dev proxy) is open and answering.
 */
async function liveRoomAnswers(page: Page): Promise<void> {
  const socket = await page.waitForEvent('websocket', (ws) => ws.url().includes('/colyseus/'))
  await socket.waitForEvent('framereceived')
}

test('the overview dashboard loads without console errors', async ({ signedIn, browserLog }) => {
  const org = await seedOrg({ members: [{ key: 'dev', role: 'developer', name: 'Gale Overview' }] })
  const page = await signedIn(org.members.dev)
  const live = liveRoomAnswers(page)
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/, Gale$/)
  await expect(page.getByRole('radio', { name: 'Overview' })).toBeChecked()
  await expect(page.getByRole('button', { name: 'Standup' })).toBeVisible()
  await live
  expect(browserLog.consoleErrors).toEqual([])
})

test('the garden loads its scene and joins the live room without errors', async ({ signedIn, browserLog }) => {
  test.slow() // The scene builds on a software GPU in headless runs.
  const org = await seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  const live = liveRoomAnswers(page)
  await page.goto('/dashboard?view=garden')
  await expect(page.getByRole('radio', { name: 'Garden' })).toBeChecked()
  await expect(page.locator('canvas').first()).toBeVisible()

  const loading = page.getByRole('status', { name: /^Loading the garden/ })
  await expect(loading).toBeVisible()
  await expect(loading).toBeHidden({ timeout: 90_000 })
  await live
  await expect(page.getByText(/Live dashboard disconnected|Reconnecting to live dashboard/)).toHaveCount(0)
  expect(browserLog.consoleErrors).toEqual([])
})
