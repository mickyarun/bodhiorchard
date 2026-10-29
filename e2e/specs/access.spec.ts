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

/** Who sees which screens, and that one org never sees another's work. */
import { createBud } from '../fixtures/api.ts'
import { expect, test } from '../fixtures/test.ts'
import { budCard } from '../screens/buds.ts'
import { navLink, openSettingsGroup } from '../screens/shell.ts'

test('an admin reaches settings and member management', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'admin', role: 'admin' }] })
  const page = await signedIn(org.members.admin)
  await page.goto('/dashboard')
  await expect(navLink(page, 'Members')).toBeVisible()
  await openSettingsGroup(page)
  await expect(navLink(page, 'Integrations')).toBeVisible()

  await navLink(page, 'Integrations').click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('heading', { name: 'Integrations', level: 2 })).toBeVisible()

  await page.goto('/members')
  await expect(page.getByRole('heading', { name: 'Members', level: 1 })).toBeVisible()
  const sections = page.getByRole('tablist', { name: 'Members sections' })
  for (const tab of ['People', 'Teams', 'Roles']) {
    await expect(sections.getByRole('tab', { name: tab })).toBeVisible()
  }
})

test('a developer is kept out of the admin screens', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/dashboard')
  await expect(navLink(page, 'Board')).toBeVisible()
  await expect(navLink(page, 'Members')).toHaveCount(0)
  await openSettingsGroup(page)
  await expect(navLink(page, 'MCP connect')).toBeVisible()
  await expect(navLink(page, 'Integrations')).toHaveCount(0)

  for (const path of ['/members', '/settings', '/settings/leave', '/triage']) {
    await page.goto(path)
    await expect(page, `${path} sends a developer home`).toHaveURL(/\/dashboard$/)
  }
})

test('HR works in People and never lands in engineering', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'hr', role: 'hr' }] })
  const page = await signedIn(org.members.hr)
  await page.goto('/')
  await expect(page).toHaveURL(/\/leave$/)
  await expect(navLink(page, 'Employees')).toBeVisible()
  await expect(navLink(page, 'Board')).toHaveCount(0)

  await page.goto('/buds')
  await expect(page).toHaveURL(/\/leave$/)
})

test("one org never sees another org's BUDs", async ({ signedIn, stack }) => {
  const [alpha, beta] = await Promise.all([
    stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] }),
    stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] }),
  ])
  const secret = await createBud(await stack.api(alpha.members.pm), 'Alpha acquisition plan')
  const betaApi = await stack.api(beta.members.pm)
  await createBud(betaApi, 'Beta onboarding revamp')

  const page = await signedIn(beta.members.pm)
  await page.goto('/buds')
  await expect(budCard(page, 'Beta onboarding revamp')).toBeVisible()
  await expect(page.getByText('Alpha acquisition plan')).toHaveCount(0)

  await page.goto(`/buds/${secret.id}`)
  await expect(page.getByText("This BUD didn't load")).toBeVisible()
  await expect(page.getByText('Alpha acquisition plan')).toHaveCount(0)
  expect(await betaApi.statusOf(`buds/${secret.id}`)).toBe(404)
})
