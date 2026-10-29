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

/** The feature registry a scan builds, and reporting bugs against it. */
import { expect, test } from '../fixtures/test.ts'

test('the feature registry lists what the scan found and search narrows it', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  await stack.addFeatures(org, [
    { title: 'Feature: Invoice export', description: 'Download invoices as CSV or PDF.' },
    { title: 'Feature: Password reset', description: 'Email a one-time reset link.' },
  ])
  const page = await signedIn(org.members.dev)
  await page.goto('/features')
  await expect(page.getByRole('heading', { name: 'Features', level: 1 })).toBeVisible()
  await expect(page.getByText('Invoice export').first()).toBeVisible()
  await expect(page.getByText('Password reset').first()).toBeVisible()

  await page.getByRole('textbox', { name: 'Search features' }).fill('invoice')
  await expect(page.getByText('Password reset')).toHaveCount(0)
  await expect(page.getByText('Invoice export').first()).toBeVisible()
})

test('an empty registry says so', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/features')
  await expect(page.getByRole('heading', { name: 'No features mapped yet' })).toBeVisible()
})

test('a developer reports a bug and opens it from the list', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer', name: 'Quinn Tester' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/bugs')
  await expect(page.getByRole('heading', { name: 'Bugs', level: 1 })).toBeVisible()

  await page.getByRole('button', { name: 'Report a bug' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Report a bug' })).toBeVisible()
  // Nothing to send without a title.
  await expect(dialog.getByRole('button', { name: 'Report bug' })).toBeDisabled()

  await dialog.getByLabel(/^Title/).fill('Checkout button does nothing on Safari')
  await dialog.getByLabel('Description').fill('Clicking Pay shows no spinner and no order is placed.')
  await dialog.getByRole('button', { name: 'Report bug' }).click()
  await expect(dialog).toBeHidden()

  const list = page.getByRole('region', { name: 'Bugs' })
  const bug = list.getByRole('button', { name: /Checkout button does nothing on Safari/ })
  await expect(bug).toBeVisible()
  await bug.click()
  await expect(page.getByText('Clicking Pay shows no spinner and no order is placed.')).toBeVisible()
})
