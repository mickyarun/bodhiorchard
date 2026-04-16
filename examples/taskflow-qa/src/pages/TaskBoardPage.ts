import { type Page, type Locator } from '@playwright/test'

export class TaskBoardPage {
  readonly page: Page
  readonly heading: Locator
  readonly newTaskButton: Locator
  readonly taskCards: Locator
  readonly searchInput: Locator

  constructor(page: Page) {
    this.page = page
    // TaskBoard.vue renders <h1>Task Board</h1> — the old /tasks/i regex
    // doesn't match because there's no trailing 's' on "Task".
    this.heading = page.getByRole('heading', { name: /task board/i })
    this.newTaskButton = page.getByRole('button', { name: /new task/i })
    // Example app uses class="task-card", not data-testid="task-card".
    // Adding a data-testid would be more robust but requires changing the
    // example app itself — out of scope for this test suite.
    this.taskCards = page.locator('.task-card')
    // NOTE: the example TaskBoard.vue does NOT have a search input. Tests
    // that use this locator are skipped until the feature ships.
    this.searchInput = page.getByPlaceholder(/search/i)
  }

  async goto(): Promise<void> {
    await this.page.goto('/tasks')
  }

  async createTask(title: string, description?: string): Promise<void> {
    await this.newTaskButton.click()
    await this.page.getByLabel('Title').fill(title)
    if (description) {
      await this.page.getByLabel('Description').fill(description)
    }
    await this.page.getByRole('button', { name: /create|save/i }).click()
  }

  async searchTasks(query: string): Promise<void> {
    await this.searchInput.fill(query)
  }

  async getTaskCount(): Promise<number> {
    return this.taskCards.count()
  }
}
