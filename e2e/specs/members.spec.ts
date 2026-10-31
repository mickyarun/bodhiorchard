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

/** Members: adding people, their roles, custom roles, and who may do what. */
import { expect, test } from '../fixtures/test.ts'
import { pickOption, unique } from '../screens/forms.ts'

test('an owner adds a member, changes their role and deactivates them', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'owner', role: 'org_owner' }] })
  const page = await signedIn(org.members.owner)
  await page.goto('/members')
  await expect(page.getByRole('heading', { name: 'Members', level: 1 })).toBeVisible()

  const name = `Nia ${unique()}`
  await page.getByRole('button', { name: 'Add member' }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Add member' })
  await dialog.getByLabel('Name').fill(name)
  await dialog.getByLabel('Email').fill(`nia-${unique()}@e2e.example.com`)
  await dialog.getByLabel('Starting password').fill('Starting-pass-1')
  await pickOption(dialog, 'Role (optional)', 'Developer')
  await dialog.getByRole('button', { name: 'Add member' }).click()
  await expect(dialog).toBeHidden()

  const role = page.getByRole('combobox', { name: `Role for ${name}` })
  await expect(role).toHaveValue('Developer')
  // The picker shows the new role only once it is saved.
  await pickOption(page, `Role for ${name}`, 'QA')
  await expect(role).toHaveValue('QA')
  await page.reload()
  await expect(page.getByRole('combobox', { name: `Role for ${name}` })).toHaveValue('QA')

  await page.getByRole('button', { name: `More for ${name}` }).click()
  await page.getByRole('menu', { name: `More for ${name}` }).getByRole('menuitem', { name: 'Deactivate' }).click()
  await expect(page.getByRole('combobox', { name: `Role for ${name}` })).toHaveCount(0)
  await pickOption(page, 'Show', /^Inactive/)
  await expect(page.getByRole('combobox', { name: `Role for ${name}` })).toBeDisabled()
})

test('a custom role grants exactly the permissions it lists', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'owner', role: 'org_owner' }, { key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.owner)
  await page.goto('/members?tab=roles')
  await page.getByRole('button', { name: 'Create role' }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Create role' })
  const roleName = `Release captain ${unique()}`
  await dialog.getByLabel('Role name').fill(roleName)
  const create = dialog.getByRole('button', { name: 'Create', exact: true })
  await expect(create).toBeDisabled()
  await dialog.getByRole('button', { name: /^Workspaces/ }).click()
  await dialog.getByRole('checkbox', { name: 'Access Engineering Workspace' }).check()
  await create.click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText(roleName)).toBeVisible()

  await page.goto('/members')
  const saved = page.waitForResponse((r) => r.url().endsWith(`/members/${org.members.dev.id}/role`) && r.ok())
  await pickOption(page, `Role for ${org.members.dev.name}`, roleName)
  await saved
  const me = await (await stack.api(org.members.dev)).get<{ permissions: string[] }>('auth/me')
  expect(me.permissions).toEqual(['workspace:engineering'])
})

test('a manager manages members but cannot add them or hand out org owner', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'mgr', role: 'manager' }, { key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.mgr)
  // The page must not ask for settings a manager may not read.
  const connections: string[] = []
  page.on('request', (r) => { if (r.url().includes('/api/v1/settings/connections')) connections.push(r.url()) })
  await page.goto('/members')
  await expect(page.getByRole('combobox', { name: `Role for ${org.members.dev.name}` })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add member' })).toHaveCount(0)

  await pickOption(page, `Role for ${org.members.dev.name}`, 'Org Owner')
  await expect(page.getByText('Only the org owner can assign the org owner role.')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('combobox', { name: `Role for ${org.members.dev.name}` })).toHaveValue('Developer')
  expect(connections).toEqual([])
})
