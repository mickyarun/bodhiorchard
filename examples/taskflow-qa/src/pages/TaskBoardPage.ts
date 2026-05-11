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
