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

/** Form controls Vuetify renders in ways a plain `fill` can't drive. */
import { expect, type Locator, type Page } from '@playwright/test'

/**
 * Opens a select or autocomplete by its label and picks one option. It opens
 * from the keyboard, as a keyboard user would: Vuetify keeps the input itself
 * transparent, so there is nothing visible to click on.
 */
export async function pickOption(scope: Page | Locator, label: string | RegExp, option: string | RegExp): Promise<void> {
  const page = 'page' in scope ? scope.page() : scope
  await scope.getByRole('combobox', { name: label }).press('ArrowDown')
  const choice = page.getByRole('option', { name: option, exact: typeof option === 'string' })
  await expect(choice).toBeVisible()
  await choice.click()
}

/** A random suffix for names and emails a test types itself. */
export function unique(): string {
  return Math.random().toString(36).slice(2, 8)
}
