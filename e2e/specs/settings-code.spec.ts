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

/** Settings → Code: repositories added from a local folder, then removed. */
import path from 'node:path'
import { makeGitRepo } from '../fixtures/git.ts'
import { expect, test } from '../fixtures/test.ts'

test('an owner adds a repository from a local folder and removes it', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'owner', role: 'org_owner' }] })
  const repo = path.basename(makeGitRepo('ledger-api'))
  const page = await signedIn(org.members.owner)
  await page.goto('/settings/code')
  await expect(page.getByRole('heading', { name: 'Code', level: 1 })).toBeVisible()
  await expect(page.getByText('No repositories yet — add one to get started.')).toBeVisible()

  await page.getByRole('button', { name: 'Add repo' }).click()
  const add = page.getByRole('dialog').filter({ hasText: 'Add repositories' })
  await add.getByRole('button', { name: 'Choose folders' }).click()
  const picker = page.getByRole('dialog').filter({ hasText: 'Select Repositories' })
  await picker.getByText('repos', { exact: true }).click()
  await picker.getByRole('checkbox', { name: `Select ${repo}` }).check()
  await picker.getByRole('button', { name: 'Add 1 Repo' }).click()

  // No scan: it would run the (faked) agent and isn't what this test is about.
  await add.getByRole('checkbox', { name: 'Scan after adding' }).uncheck()
  await add.getByRole('button', { name: 'Add 1 repository' }).click()
  await expect(add).toBeHidden()
  await expect(page.getByText(repo, { exact: true })).toBeVisible()

  await page.getByRole('button', { name: `Actions for ${repo}` }).click()
  await page.getByRole('menuitem', { name: 'Remove' }).click()
  const confirm = page.getByRole('dialog').filter({ hasText: 'Remove repository?' })
  await confirm.getByRole('button', { name: 'Remove', exact: true }).click()
  await expect(page.getByText('No repositories yet — add one to get started.')).toBeVisible()
})

test('a developer is kept out of the repository settings', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/settings/code')
  // Settings → Code needs Configure Integrations; a developer is sent home.
  await expect(page).toHaveURL(/\/dashboard$/)
})
