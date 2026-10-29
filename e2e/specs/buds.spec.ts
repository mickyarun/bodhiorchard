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
import type { Page } from '@playwright/test'
import { Api, createBud } from '../fixtures/api.ts'
import { seedOrg } from '../fixtures/stack.ts'
import { expect, test } from '../fixtures/test.ts'

const STAGE_AGENTS = ['PRD writer', 'Design', 'Tech plan', 'Test plan', 'Learning recap']

const sections = (page: Page) => page.getByRole('tablist', { name: 'BUD sections' })

async function expectSection(page: Page, tab: string): Promise<void> {
  await expect(sections(page).getByRole('tab', { name: tab })).toHaveAttribute('aria-selected', 'true')
}

test('a PM creates a BUD from the board and lands on its requirements', async ({ signedIn }) => {
  const org = await seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const page = await signedIn(org.members.pm)
  await page.goto('/buds')
  await expect(page.getByRole('heading', { name: 'Board', level: 1 })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'No BUDs yet' })).toBeVisible()

  await page.getByRole('button', { name: 'New BUD' }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'New BUD' })).toBeVisible()
  await dialog.getByLabel('Title').fill('Export invoices as CSV')
  await dialog.getByRole('radio', { name: 'P1' }).click()
  // Every stage agent starts switched on; this BUD is written by hand. Each
  // switch is named, so one that renders late is waited for, not skipped.
  await dialog.getByText('Advanced settings').click()
  for (const stage of STAGE_AGENTS) {
    const toggle = dialog.getByRole('checkbox', { name: `Auto-generate ${stage}` })
    await toggle.uncheck()
    await expect(toggle).not.toBeChecked()
  }
  await dialog.getByRole('button', { name: 'Create' }).click()

  await expect(page).toHaveURL(/\/buds\/[0-9a-f-]{36}/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Export invoices as CSV/)
  await expect(page.getByText("Stage agents are off. You're driving this BUD.")).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('BUD-001')
  await expectSection(page, 'Requirements')

  await page.getByRole('navigation', { name: 'Breadcrumb' }).getByRole('link', { name: 'Board' }).click()
  await expect(page.getByRole('link', { name: /Export invoices as CSV/ })).toBeVisible()
})

test('moving a BUD through its stages opens each stage tab', async ({ signedIn }) => {
  const org = await seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const api = await Api.as(org.members.pm)
  const bud = await createBud(api, 'Rate limit the public API')
  await api.dispose()

  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await expectSection(page, 'Requirements')

  for (const [stage, tab] of [['Design', 'Design'], ['Tech Architecture', 'Tech spec'], ['Development', 'Development']]) {
    await page.getByRole('button', { name: `Move to ${stage}` }).click()
    await expectSection(page, tab)
  }

  // A section deep link survives a reload; an unknown one is ignored.
  await page.goto(`/buds/${bud.id}?tab=testing`)
  await expectSection(page, 'Testing')
  await page.goto(`/buds/${bud.id}?tab=not-a-section`)
  await expectSection(page, 'Development')
})

test('a developer can open BUDs but not create them', async ({ signedIn }) => {
  const org = await seedOrg({ members: [{ key: 'pm', role: 'pm' }, { key: 'dev', role: 'developer' }] })
  const api = await Api.as(org.members.pm)
  await createBud(api, 'Nightly backup report')
  await api.dispose()

  const page = await signedIn(org.members.dev)
  await page.goto('/buds')
  await expect(page.getByRole('link', { name: /Nightly backup report/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'New BUD' })).toHaveCount(0)
})
