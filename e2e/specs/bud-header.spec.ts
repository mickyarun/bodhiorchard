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

/** The BUD header: priority, assignee, AI skills, and deleting a BUD. */
import { createBud } from '../fixtures/api.ts'
import { expect, test } from '../fixtures/test.ts'
import { budCard, openBudMenu } from '../screens/buds.ts'

test('a PM changes priority and assignee, and the AI skills choice is kept', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }, { key: 'dev', role: 'developer', name: 'Dana Builder' }] })
  const bud = await createBud(await stack.api(org.members.pm), 'Usage-based pricing')
  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)

  await page.getByRole('button', { name: /^Priority P2/ }).click()
  await page.getByRole('menu', { name: 'Priority' }).getByRole('menuitemradio', { name: 'P0' }).click()
  await expect(page.getByRole('button', { name: /^Priority P0/ })).toBeVisible()

  // The header's button; the Details panel has a plain "Change assignee" too.
  await page.getByRole('button', { name: /\. Change assignee$/ }).click()
  await page.getByLabel('Search members').fill('Dana')
  await page.getByRole('listbox', { name: 'Members' }).getByRole('option', { name: /^Dana Builder/ }).click()
  await expect(page.getByRole('button', { name: /^Assigned to Dana Builder/ })).toBeVisible()

  await (await openBudMenu(page)).getByRole('menuitem', { name: 'AI skills' }).click()
  const skills = page.getByRole('dialog').filter({ hasText: 'AI skills for this BUD' })
  await skills.getByRole('checkbox', { name: 'Auto-generate Test plan' }).check()
  await skills.getByRole('button', { name: 'Save' }).click()
  await expect(skills).toBeHidden()
  await page.reload()
  await (await openBudMenu(page)).getByRole('menuitem', { name: 'AI skills' }).click()
  await expect(page.getByRole('dialog').getByRole('checkbox', { name: 'Auto-generate Test plan' })).toBeChecked()
})

test('deleting a BUD asks first, then takes it off the board', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'owner', role: 'org_owner' }] })
  const api = await stack.api(org.members.owner)
  const bud = await createBud(api, 'Throwaway experiment')
  await createBud(api, 'Keeper experiment')
  const page = await signedIn(org.members.owner)
  await page.goto(`/buds/${bud.id}`)
  await (await openBudMenu(page)).getByRole('menuitem', { name: 'Delete BUD' }).click()
  await page.getByRole('dialog').filter({ hasText: 'Delete this BUD?' }).getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(page).toHaveURL(/\/buds$/)
  // The other BUD's card says the board has loaded.
  await expect(budCard(page, 'Keeper experiment')).toBeVisible()
  await expect(budCard(page, 'Throwaway experiment')).toHaveCount(0)
})
