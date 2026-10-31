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

/** Settings owned by People: offices, leave policies, and the company quiz. */
import { expect, test } from '../fixtures/test.ts'
import { unique } from '../screens/forms.ts'

test('HR adds an office, renames it and deletes it', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'hr', role: 'hr' }] })
  const page = await signedIn(org.members.hr)
  await page.goto('/settings/offices')
  await expect(page.getByRole('heading', { name: 'Offices', level: 1 })).toBeVisible()
  await expect(page.getByText('No offices yet')).toBeVisible()

  const name = `Lisbon ${unique()}`
  await page.getByRole('button', { name: 'Add office' }).click()
  const add = page.getByRole('dialog').filter({ hasText: 'Add office' })
  await add.getByLabel('Name').fill(name)
  await add.getByLabel('City').fill('Lisbon')
  await add.getByLabel('Country').fill('PT')
  await add.getByRole('button', { name: 'Add office' }).click()
  await expect(add).toBeHidden()
  await expect(page.getByRole('row').filter({ hasText: name })).toBeVisible()

  await page.getByRole('button', { name: `Edit ${name}` }).click()
  const edit = page.getByRole('dialog').filter({ hasText: 'Edit office' })
  await edit.getByLabel('Name').fill(`${name} HQ`)
  await edit.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('row').filter({ hasText: `${name} HQ` })).toBeVisible()

  await page.getByRole('button', { name: `Delete ${name} HQ` }).click()
  await page.getByRole('dialog').filter({ hasText: 'Delete this office?' }).getByRole('button', { name: 'Delete office' }).click()
  await expect(page.getByText('No offices yet')).toBeVisible()
})

test('HR adds a leave policy', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'hr', role: 'hr' }] })
  const page = await signedIn(org.members.hr)
  await page.goto('/settings/leave')
  await expect(page.getByRole('heading', { name: 'Leave', level: 1 })).toBeVisible()

  const name = `UK London ${unique()}`
  await page.getByRole('button', { name: 'Add policy' }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Add policy' })
  await dialog.getByLabel('Name').fill(name)
  await dialog.getByRole('button', { name: 'Create policy' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText(name).first()).toBeVisible()
})

test('a quiz master turns the company quiz on, and it stays on', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'qm', role: 'quiz_master' }] })
  const page = await signedIn(org.members.qm)
  await page.goto('/settings/quiz-game')
  await expect(page.getByRole('heading', { name: 'Quiz Game', level: 1 })).toBeVisible()

  const enabled = page.getByRole('checkbox', { name: 'Enable the company quiz' })
  await expect(enabled).not.toBeChecked()
  await enabled.check()
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Settings saved.')).toBeVisible()

  await page.reload()
  await expect(enabled).toBeChecked()
})
