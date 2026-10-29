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

/** The BUD board, the New BUD dialog and the BUD detail page. */
import { expect, type Locator, type Page } from '@playwright/test'

export type Priority = 'P0' | 'P1' | 'P2' | 'P3'

const STAGE_AGENTS = ['PRD writer', 'Design', 'Tech plan', 'Test plan', 'Learning recap']

export function budCard(page: Page, title: string): Locator {
  return page.getByRole('link', { name: new RegExp(title) })
}

/**
 * Fills New BUD from the board and creates it, with every stage agent
 * switched off (they start on). Each switch is named, so one that renders
 * late is waited for, not skipped.
 */
export async function createBudFromBoard(page: Page, title: string, priority: Priority = 'P2'): Promise<void> {
  await page.getByRole('button', { name: 'New BUD' }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'New BUD' })).toBeVisible()
  await dialog.getByLabel('Title').fill(title)
  await dialog.getByRole('radio', { name: priority }).click()
  await dialog.getByText('Advanced settings').click()
  for (const stage of STAGE_AGENTS) {
    const toggle = dialog.getByRole('checkbox', { name: `Auto-generate ${stage}` })
    await toggle.uncheck()
    await expect(toggle).not.toBeChecked()
  }
  await dialog.getByRole('button', { name: 'Create' }).click()
}

export function budSections(page: Page): Locator {
  return page.getByRole('tablist', { name: 'BUD sections' })
}

export async function expectSection(page: Page, tab: string): Promise<void> {
  await expect(budSections(page).getByRole('tab', { name: tab })).toHaveAttribute('aria-selected', 'true')
}

/** "Move to <stage>" in the header, then the stage's own tab opens. */
export async function moveBudTo(page: Page, stage: string, tab: string): Promise<void> {
  await page.getByRole('button', { name: `Move to ${stage}` }).click()
  await expectSection(page, tab)
}
