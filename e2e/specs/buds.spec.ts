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

/** The BUD board, creating a BUD, and moving it through its stages. */
import { createBud } from '../fixtures/api.ts'
import { expect, test } from '../fixtures/test.ts'
import { budCard, createBudFromBoard, expectSection, moveBudTo } from '../screens/buds.ts'

test('a PM creates a BUD from the board and lands on its requirements', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const page = await signedIn(org.members.pm)
  await page.goto('/buds')
  await expect(page.getByRole('heading', { name: 'Board', level: 1 })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'No BUDs yet' })).toBeVisible()

  await createBudFromBoard(page, 'Export invoices as CSV', 'P1')
  await expect(page).toHaveURL(/\/buds\/[0-9a-f-]{36}/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Export invoices as CSV/)
  await expect(page.getByText("Stage agents are off. You're driving this BUD.")).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('BUD-001')
  await expectSection(page, 'Requirements')

  await page.getByRole('navigation', { name: 'Breadcrumb' }).getByRole('link', { name: 'Board' }).click()
  await expect(budCard(page, 'Export invoices as CSV')).toBeVisible()
})

test('moving a BUD through its stages opens each stage tab', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const bud = await createBud(await stack.api(org.members.pm), 'Rate limit the public API')

  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await expectSection(page, 'Requirements')
  await moveBudTo(page, 'Design', 'Design')
  await moveBudTo(page, 'Tech Architecture', 'Tech spec')
  await moveBudTo(page, 'Development', 'Development')

  // A section deep link survives a reload; an unknown one is ignored.
  await page.goto(`/buds/${bud.id}?tab=testing`)
  await expectSection(page, 'Testing')
  await page.goto(`/buds/${bud.id}?tab=not-a-section`)
  await expectSection(page, 'Development')
})

test('a developer can open BUDs but not create them', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }, { key: 'dev', role: 'developer' }] })
  await createBud(await stack.api(org.members.pm), 'Nightly backup report')

  const page = await signedIn(org.members.dev)
  await page.goto('/buds')
  await expect(budCard(page, 'Nightly backup report')).toBeVisible()
  await expect(page.getByRole('button', { name: 'New BUD' })).toHaveCount(0)
})
