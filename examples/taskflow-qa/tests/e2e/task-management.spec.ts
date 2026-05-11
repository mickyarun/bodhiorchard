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

import { test, expect } from '@playwright/test'
import { LoginPage } from '../../src/pages/LoginPage'
import { TaskBoardPage } from '../../src/pages/TaskBoardPage'
import { TEST_USER, testTask } from '../../src/helpers/test-data'

test.describe('Task Management', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login(TEST_USER.email, TEST_USER.password)
    await page.waitForURL(/\/tasks/)
  })

  test('task board loads and shows heading', async ({ page }) => {
    const board = new TaskBoardPage(page)
    await expect(board.heading).toBeVisible()
  })

  // The example TaskBoard.vue is a minimal stub: it declares a
  // `showCreateDialog` ref and wires the "+ New Task" button to it, but
  // no dialog is actually rendered in the template. Nothing happens when
  // the user clicks the button. Re-enable this test once the example app
  // grows a real create-task dialog with Title/Description inputs.
  test.skip('create a new task', async ({ page }) => {
    const board = new TaskBoardPage(page)
    const task = testTask({ title: 'E2E Test Task' })

    await board.createTask(task.title, task.description)

    // Verify task appears
    await expect(page.getByText(task.title)).toBeVisible()
  })

  // The example TaskBoard.vue has no search input at all — there's no
  // <input placeholder="search..."> in the template. Re-enable this test
  // once search lands in the example app.
  test.skip('search filters tasks', async ({ page }) => {
    const board = new TaskBoardPage(page)

    await board.searchTasks('nonexistent-query-12345')
    // Should show empty or filtered state
    const count = await board.getTaskCount()
    expect(count).toBe(0)
  })
})
