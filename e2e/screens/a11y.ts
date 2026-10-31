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
 * An automated accessibility check: axe-core against WCAG 2.1 A and AA.
 * Serious and critical findings fail; minor and moderate ones are left to
 * review, as they are often judgement calls axe can't make.
 *
 * Closed Vuetify overlays are skipped: a tooltip can leave its root in the
 * page while closed (inside an eager tab, say), with its content hidden, so
 * it presents nothing to a user or a screen reader. Open ones are checked.
 *
 * The check waits for running transitions first: a menu caught mid fade-in
 * is part transparent, and axe reads that as low contrast everywhere in it.
 */
import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']
const FAILING = new Set(['serious', 'critical'])
const CLOSED_OVERLAYS = '.v-overlay:not(.v-overlay--active)'

export async function expectAccessible(page: Page, screen: string): Promise<void> {
  // Endless ones (spinners, the garden) never settle, so only finite ones count.
  await page.waitForFunction(() => document.getAnimations().every((a) =>
    a.playState !== 'running' || a.effect?.getComputedTiming().endTime === Infinity))
  const results = await new AxeBuilder({ page }).withTags(WCAG_21_AA).exclude(CLOSED_OVERLAYS).analyze()
  const found = results.violations
    .filter((violation) => FAILING.has(violation.impact ?? ''))
    .flatMap((violation) => violation.nodes.map((node) =>
      `${violation.impact} ${violation.id}: ${node.target.join(' ')} (${violation.help})`))
  expect(found, `accessibility problems on ${screen}`).toEqual([])
}
