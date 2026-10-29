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
import type { Page } from '@playwright/test'
import { Api, createBud } from '../fixtures/api.ts'
import { seedOrg } from '../fixtures/stack.ts'
import { expect, test } from '../fixtures/test.ts'

const sidebar = (page: Page) => page.getByRole('navigation').first()

async function openSettingsGroup(page: Page): Promise<void> {
  await sidebar(page).getByRole('option', { name: 'Settings' }).or(
    sidebar(page).getByText('Settings', { exact: true }),
  ).first().click()
}

test('an admin reaches settings and member management', async ({ signedIn }) => {
  const org = await seedOrg({ members: [{ key: 'admin', role: 'admin' }] })
  const page = await signedIn(org.members.admin)
  await page.goto('/dashboard')
  await expect(sidebar(page).getByRole('link', { name: 'Members', exact: true })).toBeVisible()
  await openSettingsGroup(page)
  await expect(sidebar(page).getByRole('link', { name: 'Integrations', exact: true })).toBeVisible()

  await sidebar(page).getByRole('link', { name: 'Integrations', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('heading', { name: 'Integrations', level: 2 })).toBeVisible()

  await page.goto('/members')
  await expect(page.getByRole('heading', { name: 'Members', level: 1 })).toBeVisible()
  const sections = page.getByRole('tablist', { name: 'Members sections' })
  for (const tab of ['People', 'Teams', 'Roles']) {
    await expect(sections.getByRole('tab', { name: tab })).toBeVisible()
  }
})

test('a developer is kept out of the admin screens', async ({ signedIn }) => {
  const org = await seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/dashboard')
  await expect(sidebar(page).getByRole('link', { name: 'Board', exact: true })).toBeVisible()
  await expect(sidebar(page).getByRole('link', { name: 'Members', exact: true })).toHaveCount(0)
  await openSettingsGroup(page)
  await expect(sidebar(page).getByRole('link', { name: 'MCP connect', exact: true })).toBeVisible()
  await expect(sidebar(page).getByRole('link', { name: 'Integrations', exact: true })).toHaveCount(0)

  for (const path of ['/members', '/settings', '/settings/leave', '/triage']) {
    await page.goto(path)
    await expect(page, `${path} sends a developer home`).toHaveURL(/\/dashboard$/)
  }
})

test('HR works in People and never lands in engineering', async ({ signedIn }) => {
  const org = await seedOrg({ members: [{ key: 'hr', role: 'hr' }] })
  const page = await signedIn(org.members.hr)
  await page.goto('/')
  await expect(page).toHaveURL(/\/leave$/)
  await expect(sidebar(page).getByRole('link', { name: 'Employees', exact: true })).toBeVisible()
  await expect(sidebar(page).getByRole('link', { name: 'Board', exact: true })).toHaveCount(0)

  await page.goto('/buds')
  await expect(page).toHaveURL(/\/leave$/)
})

test("one org never sees another org's BUDs", async ({ signedIn }) => {
  const [alpha, beta] = await Promise.all([
    seedOrg({ members: [{ key: 'pm', role: 'pm' }] }),
    seedOrg({ members: [{ key: 'pm', role: 'pm' }] }),
  ])
  const alphaApi = await Api.as(alpha.members.pm)
  const secret = await createBud(alphaApi, 'Alpha acquisition plan')
  await alphaApi.dispose()
  const betaApi = await Api.as(beta.members.pm)
  await createBud(betaApi, 'Beta onboarding revamp')

  const page = await signedIn(beta.members.pm)
  await page.goto('/buds')
  await expect(page.getByRole('link', { name: /Beta onboarding revamp/ })).toBeVisible()
  await expect(page.getByText('Alpha acquisition plan')).toHaveCount(0)

  await page.goto(`/buds/${secret.id}`)
  await expect(page.getByText("This BUD didn't load")).toBeVisible()
  await expect(page.getByText('Alpha acquisition plan')).toHaveCount(0)
  expect(await betaApi.statusOf(`buds/${secret.id}`)).toBe(404)
  await betaApi.dispose()
})
