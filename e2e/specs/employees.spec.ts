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

/** The employee directory and the encrypted bank and ID details. */
import { expect, test } from '../fixtures/test.ts'

test('HR saves bank details, sees them masked, and a reveal is logged', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({
    members: [
      { key: 'hr', role: 'hr', name: 'Hana People' },
      { key: 'emp', role: 'developer', name: 'Iris Engineer' },
    ],
  })
  const hr = await signedIn(org.members.hr)
  await hr.goto('/people')
  await expect(hr.getByRole('heading', { name: 'Employees', level: 1 })).toBeVisible()
  await hr.getByRole('link', { name: 'Iris Engineer' }).click()
  await expect(hr).toHaveURL(new RegExp(`/people/${org.members.emp.id}`))

  await hr.getByRole('tab', { name: /Bank and IDs/ }).click()
  await hr.getByRole('button', { name: 'Edit', exact: true }).click()
  const dialog = hr.getByRole('dialog')
  await dialog.getByLabel('Account number').fill('123456789012')
  await dialog.getByRole('button', { name: 'Save changes' }).click()
  await expect(dialog).toBeHidden()

  await expect(hr.getByText('•••• 9012')).toBeVisible()
  await expect(hr.getByText('123456789012')).toHaveCount(0)
  await hr.getByRole('button', { name: 'Reveal Account number' }).click()
  await expect(hr.getByText('123456789012')).toBeVisible()
  await hr.getByRole('button', { name: 'Hide Account number' }).click()
  await expect(hr.getByText('123456789012')).toHaveCount(0)

  const log = hr.getByRole('region', { name: 'Access log' })
  await expect(log.getByText(/Hana People/).first()).toBeVisible()
})

test('a developer has no employee directory', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/dashboard')
  await expect(page.getByRole('link', { name: 'Leave', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Employees' })).toHaveCount(0)

  await page.goto('/people')
  await expect(page).toHaveURL(/\/dashboard/)
})
