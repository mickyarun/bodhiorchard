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

/** A bug's side sheet: owner, comments, and status changes that ask first. */
import { createBug } from '../fixtures/api.ts'
import { expect, test } from '../fixtures/test.ts'
import { pickOption } from '../screens/forms.ts'

test('a bug gets an owner, a comment, and is resolved after a confirm', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({
    members: [{ key: 'pm', role: 'pm', name: 'Pat Manager' }, { key: 'dev', role: 'developer', name: 'Dev Fixer' }],
  })
  await createBug(await stack.api(org.members.pm), 'Totals round the wrong way', 'Invoice totals round half down.')

  const page = await signedIn(org.members.pm)
  await page.goto('/bugs')
  await page.getByRole('radiogroup', { name: 'Environment' }).getByRole('radio', { name: 'All' }).click()
  await page.getByRole('region', { name: 'Bugs' }).getByRole('button', { name: /Totals round the wrong way/ }).click()
  await expect(page.getByText('Invoice totals round half down.')).toBeVisible()

  await pickOption(page, 'Owner', /^Dev Fixer/)
  await expect(page.getByRole('combobox', { name: 'Owner' })).toHaveValue(/Dev Fixer/)

  await page.getByLabel('Add a comment').fill('Seen on every invoice over 1,000.')
  await page.getByRole('button', { name: 'Post' }).click()
  await expect(page.getByText('Seen on every invoice over 1,000.')).toBeVisible()
  await page.getByRole('button', { name: 'Edit comment' }).click()
  await page.getByRole('textbox', { name: 'Comment', exact: true }).fill('Seen on every invoice over 1,000 GBP.')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByText('Seen on every invoice over 1,000 GBP.')).toBeVisible()

  await pickOption(page, 'Status', 'Resolved')
  const confirm = page.getByRole('dialog').filter({ hasText: 'Mark as resolved?' })
  await confirm.getByRole('button', { name: 'Mark resolved' }).click()
  await expect(page.getByRole('combobox', { name: 'Status' })).toHaveValue('Resolved')

  // Deleting is immediate and leaves a marker in the thread.
  await page.getByRole('button', { name: 'Delete comment' }).click()
  await expect(page.getByText('[deleted]')).toBeVisible()
  await expect(page.getByText('Seen on every invoice over 1,000 GBP.')).toHaveCount(0)
})
