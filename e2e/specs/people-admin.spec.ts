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

/** HR hiring: invite a new hire, give them an employee record, and they can sign in. */
import { expect, test } from '../fixtures/test.ts'
import { pickOption, unique } from '../screens/forms.ts'

test('HR invites a new hire, adds their employee record, and they can sign in', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'hr', role: 'hr', name: 'Hana People' }] })
  const page = await signedIn(org.members.hr)
  await page.goto('/people')

  const name = `Noor ${unique()}`
  const email = `noor-${unique()}@e2e.example.com`
  await page.getByRole('button', { name: 'Invite new hire' }).click()
  const invite = page.getByRole('dialog').filter({ hasText: 'Invite new hire' })
  await invite.getByLabel('Full name').fill(name)
  await invite.getByLabel('Work email').fill(email)
  await pickOption(invite, 'Role', 'Developer')
  const password = await invite.getByLabel('Temporary password').inputValue()
  expect(password.length).toBeGreaterThanOrEqual(8)
  await invite.getByRole('button', { name: 'Invite' }).click()

  // Inviting hands straight over to the employee record for that person.
  const record = page.getByRole('dialog').filter({ hasText: 'Add employee' })
  await expect(record).toBeVisible()
  await record.getByLabel('Designation').fill('Data analyst')
  await record.getByLabel('Department').fill('Finance')
  await record.getByRole('button', { name: 'Create record' }).click()
  await expect(record).toBeHidden()

  await page.goto('/people')
  await expect(page.getByRole('region', { name: 'Employee list' }).getByRole('link', { name })).toBeVisible()
  await expect(stack.login(email, password, org.slug)).resolves.toHaveProperty('access')
})
