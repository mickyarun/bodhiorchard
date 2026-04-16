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
