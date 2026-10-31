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
 * From testing to closed: manual QA cases hold the BUD until each has a
 * result, release merges (what release detection records) move the UAT and
 * Prod tabs on, and closing or discarding ends it.
 */
import { createBud, moveBud, pendingManualCases, setUatEnabled } from '../fixtures/api.ts'
import { expect, test } from '../fixtures/test.ts'
import {
  budSections, chooseStage, expectSection, markRemainingCases, openBudMenu, recordCaseResult,
} from '../screens/buds.ts'

test('a BUD goes from testing through UAT and prod to closed', async ({ signedIn, stack }) => {
  test.slow() // Two estimate runs (uat, prod) and the close-out run on the way.
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const api = await stack.api(org.members.pm)
  const bud = await createBud(api, 'Self-serve refunds')
  const repo = await stack.addRepo(org, 'payments-api')
  await stack.setDelivery(org, bud.id, { repoIds: [repo.id] })
  await moveBud(api, bud.id, 'testing', 'Hotfix, reviewed on the call')
  await stack.setManualCases(org, bud.id, [
    { id: 'MTC-001', title: 'Refund a paid order' },
    { id: 'MTC-002', title: 'Refund twice is refused' },
  ])

  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await page.getByRole('button', { name: 'Move to UAT' }).click()
  const pending = page.getByRole('dialog').filter({ hasText: 'Manual test cases still pending' })
  await expect(pending.getByText('MTC-001')).toBeVisible()
  await pending.getByRole('button', { name: 'Open QA tab' }).click()
  await expectSection(page, 'Testing')
  await recordCaseResult(page, 'MTC-001', 'Pass')
  await markRemainingCases(page, 'Skipped')
  await expect(page.getByText('2/2 completed')).toBeVisible()
  // The panel counts a result before it is saved; Move to UAT checks the saved ones.
  await expect.poll(() => pendingManualCases(api, bud.id)).toEqual([])

  await page.getByRole('button', { name: 'Move to UAT' }).click()
  await expectSection(page, 'UAT')
  await stack.recordRelease(org, bud.id, { stage: 'uat', repoId: repo.id, prNumber: 101, title: 'Release 2026.11.1' })
  await page.reload()
  await expect(page.getByText('In UAT')).toBeVisible()
  await expect(page.getByText(/Release 2026\.11\.1/)).toBeVisible()

  await page.getByRole('button', { name: 'Move to Prod' }).click()
  await expectSection(page, 'Prod')
  await stack.recordRelease(org, bud.id, { stage: 'prod', repoId: repo.id, prNumber: 102, title: 'Release 2026.11.2' })
  await page.reload()
  await expect(page.getByText('In Production')).toBeVisible()

  await chooseStage(page, 'Closed')
  const confirm = page.getByRole('dialog').filter({ hasText: 'Close this BUD?' })
  await confirm.getByRole('button', { name: 'Close BUD' }).click()
  await expectSection(page, 'Closed')
  await expect(page.getByText('This BUD is closed')).toBeVisible()
  const menu = await openBudMenu(page)
  await expect(menu.getByRole('menuitem', { name: 'Closed, so the stage can\'t change' })).toBeDisabled()
})

test('a discarded BUD goes back to the stage it left', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const api = await stack.api(org.members.pm)
  const bud = await createBud(api, 'Dark mode for invoices')
  await moveBud(api, bud.id, 'design')

  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await chooseStage(page, 'Discarded')
  await expect(page.getByText('This BUD was discarded')).toBeVisible()

  await (await openBudMenu(page)).getByRole('menuitem', { name: 'Restore BUD' }).click()
  const restore = page.getByRole('dialog').filter({ hasText: 'Restore BUD?' })
  await restore.getByRole('button', { name: 'Restore', exact: true }).click()
  await expect(page.getByText(/restored to Design/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Move to Tech Architecture' })).toBeVisible()
})

test('with UAT turned off, testing moves straight to prod', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'owner', role: 'org_owner' }] })
  const api = await stack.api(org.members.owner)
  await setUatEnabled(api, false)
  const bud = await createBud(api, 'Weekly digest email')
  await moveBud(api, bud.id, 'testing', 'Covered by the spike')

  const page = await signedIn(org.members.owner)
  await page.goto(`/buds/${bud.id}`)
  await expectSection(page, 'Testing')
  await expect(budSections(page).getByRole('tab', { name: 'UAT' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Move to Prod' }).click()
  await expectSection(page, 'Prod')
})

test('QA records results and moves testing on, but cannot edit the BUD', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }, { key: 'qa', role: 'qa' }] })
  const pmApi = await stack.api(org.members.pm)
  const bud = await createBud(pmApi, 'Bulk user import')
  await moveBud(pmApi, bud.id, 'testing', 'Reviewed offline')
  await stack.setManualCases(org, bud.id, [{ id: 'MTC-001', title: 'Import 100 users from CSV' }])

  const page = await signedIn(org.members.qa)
  await page.goto(`/buds/${bud.id}?tab=testing`)
  await recordCaseResult(page, 'MTC-001', 'Pass')
  await expect(page.getByText('1/1 completed')).toBeVisible()
  await expect.poll(() => pendingManualCases(pmApi, bud.id)).toEqual([])
  await page.getByRole('button', { name: 'Move to UAT' }).click()
  await expectSection(page, 'UAT')

  const qaApi = await stack.api(org.members.qa)
  expect(await qaApi.patchStatusOf(`buds/${bud.id}`, { title: 'Renamed by QA' })).toBe(403)
  expect(await qaApi.patchStatusOf(`buds/${bud.id}`, { status: 'closed' })).toBe(403)
})
