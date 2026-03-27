import { type Page, type Locator } from '@playwright/test'

export class TaskBoardPage {
  readonly page: Page
  readonly heading: Locator
  readonly newTaskButton: Locator
  readonly taskCards: Locator
  readonly searchInput: Locator

  constructor(page: Page) {
    this.page = page
    this.heading = page.getByRole('heading', { name: /tasks/i })
    this.newTaskButton = page.getByRole('button', { name: /new task/i })
    this.taskCards = page.locator('[data-testid="task-card"]')
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
