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

/**
 * Into and out of code review. The PRs come from the seed (what the GitHub
 * webhook would have recorded); no stage agent runs, as every BUD here has
 * its agents off.
 */
import { createBud, moveBud } from '../fixtures/api.ts'
import { expect, test } from '../fixtures/test.ts'
import { expectSection } from '../screens/buds.ts'

test('with an open PR, a BUD moves into code review and lists the PR', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const api = await stack.api(org.members.pm)
  const bud = await createBud(api, 'Invoice CSV export')
  await moveBud(api, bud.id, 'development')
  const repo = await stack.addRepo(org, 'billing-api')
  await stack.setDelivery(org, bud.id, {
    repoIds: [repo.id],
    pullRequests: [{ repoId: repo.id, number: 42, title: 'Add CSV export', state: 'open' }],
  })

  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await page.getByRole('button', { name: 'Move to Code Review' }).click()
  await expectSection(page, 'Code review')
  await expect(page.getByRole('link', { name: 'billing-api #42 Open' })).toBeVisible()

  // The tab's own way out: override to QA, with a reason of ten characters or more.
  await page.getByRole('button', { name: 'Override to QA' }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Override code review' })
  const push = dialog.getByRole('button', { name: 'Override & Push to QA' })
  await dialog.getByLabel('Reason (required)').fill('Too short')
  await expect(push).toBeDisabled()
  await dialog.getByLabel('Reason (required)').fill('Docs-only follow-up, merged by hand')
  await push.click()
  await expectSection(page, 'Testing')
})

test('without an open PR, moving into code review asks first', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const api = await stack.api(org.members.pm)
  const bud = await createBud(api, 'Retry failed webhooks')
  await moveBud(api, bud.id, 'development')

  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await page.getByRole('button', { name: 'Move to Code Review' }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'No PR is open to review' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Proceed' }).click()
  await expectSection(page, 'Code review')
})

test('leaving code review with an unmerged PR needs a reason, which the timeline keeps', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const api = await stack.api(org.members.pm)
  const bud = await createBud(api, 'Rotate API keys')
  const repo = await stack.addRepo(org, 'auth-service')
  await stack.setDelivery(org, bud.id, {
    repoIds: [repo.id],
    pullRequests: [{ repoId: repo.id, number: 7, title: 'Key rotation', state: 'open' }],
  })
  await moveBud(api, bud.id, 'code_review')

  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await page.getByRole('button', { name: 'Move to Testing' }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Advance to Testing' })
  const advance = dialog.getByRole('button', { name: 'Advance' })
  await expect(advance).toBeDisabled()
  await dialog.getByLabel('Reason (required)').fill('Hotfix: QA starts while the PR waits for a second approver')
  await advance.click()
  await expectSection(page, 'Testing')

  await page.getByRole('button', { name: 'History' }).click()
  await expect(page.getByText(/QA starts while the PR waits/)).toBeVisible()
})

test('with every PR merged, a BUD leaves code review without being asked', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const api = await stack.api(org.members.pm)
  const bud = await createBud(api, 'Paginate the audit log')
  const repo = await stack.addRepo(org, 'audit-api')
  await stack.setDelivery(org, bud.id, {
    repoIds: [repo.id],
    pullRequests: [{ repoId: repo.id, number: 3, title: 'Cursor pagination', state: 'merged' }],
  })
  await moveBud(api, bud.id, 'code_review')

  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await expect(page.getByRole('link', { name: 'audit-api #3 Merged' })).toBeVisible()
  await page.getByRole('button', { name: 'Move to Testing' }).click()
  await expectSection(page, 'Testing')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
