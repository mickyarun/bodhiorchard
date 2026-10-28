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
 * The BUD detail page's tabs: which exist, which one a stage change opens,
 * and whether the open section can be edited or chatted about. Tab values
 * must be the ones the tab panels and ``?tab=`` links use, or the page
 * shows a blank panel.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, reactive, ref } from 'vue'

const settings = vi.hoisted(() => ({
  connections: { budStages: { uatEnabled: true } } as { budStages?: { uatEnabled: boolean } },
}))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => settings }))

import { useBudDetailTabs } from '@/composables/useBudDetailTabs'
import { BUD_STATUS_ORDER, VALID_BUD_TABS, type BUDDocument, type BUDStatus } from '@/types'
import { STATUS_TAB_MAP, detailTabs } from '@/utils/budDetail'

function budRef(status: BUDStatus, extra: Partial<BUDDocument> = {}) {
  return ref({ id: 'bud-1', status, designs: [], has_learning: false, ...extra } as unknown as BUDDocument)
}

function tabsFor(bud: ReturnType<typeof budRef>) {
  return useBudDetailTabs(computed(() => bud.value))
}

beforeEach(() => {
  settings.connections = reactive({ budStages: { uatEnabled: true } })
})

describe('tab values', () => {
  it('opens every status on a tab that deep links accept', () => {
    for (const status of BUD_STATUS_ORDER) {
      expect(VALID_BUD_TABS.has(STATUS_TAB_MAP[status])).toBe(true)
    }
  })

  it('accepts the release and ended tabs, which have no section', () => {
    for (const tab of ['uat', 'prod', 'closed']) expect(VALID_BUD_TABS.has(tab)).toBe(true)
  })

  it('shows the tab each status opens on, when UAT is on', () => {
    for (const status of BUD_STATUS_ORDER) {
      const values = detailTabs({ uatEnabled: true, status, hasLearning: false }).map(t => t.value)
      expect(values).toContain(STATUS_TAB_MAP[status])
    }
  })
})

describe('useBudDetailTabs', () => {
  it('has no tabs before the BUD loads', () => {
    const t = useBudDetailTabs(computed(() => null))
    expect(t.tabs.value).toEqual([])
    expect(t.activeTab.value).toBe('requirements')
  })

  it('follows the org UAT setting and shows Closed and Learnings once there is something to show', () => {
    settings.connections.budStages!.uatEnabled = false
    const t = tabsFor(budRef('closed', { has_learning: true }))
    const values = t.tabs.value.map(x => x.value)
    expect(values).not.toContain('uat')
    expect(values.slice(-2)).toEqual(['closed', 'learnings'])
    expect(t.isClosed.value).toBe(true)
  })

  it('assumes UAT is on until the settings arrive', () => {
    settings.connections = reactive({})
    expect(tabsFor(budRef('testing')).uatStageEnabled.value).toBe(true)
  })

  it('opens the new stage tab when the open BUD changes stage', async () => {
    const bud = budRef('tech_arch')
    const t = tabsFor(bud)
    t.activeTab.value = 'requirements'
    bud.value = { ...bud.value, status: 'development' }
    await nextTick()
    expect(t.activeTab.value).toBe('development')
  })

  it('leaves the tab alone when another BUD loads', async () => {
    const bud = budRef('tech_arch')
    const t = tabsFor(bud)
    t.activeTab.value = 'testing'
    bud.value = { ...bud.value, id: 'bud-2', status: 'design' }
    await nextTick()
    expect(t.activeTab.value).toBe('testing')
  })

  it('falls back to Prod when UAT is switched off while its tab is open', async () => {
    const t = tabsFor(budRef('uat'))
    t.activeTab.value = 'uat'
    settings.connections.budStages!.uatEnabled = false
    await nextTick()
    expect(t.activeTab.value).toBe('prod')
  })

  it('hides the section toolbar on the read-only tabs', () => {
    const t = tabsFor(budRef('bud'))
    for (const tab of ['development', 'code-review', 'testing', 'uat', 'prod', 'closed']) {
      t.activeTab.value = tab
      expect(t.isReadOnlyTab.value).toBe(true)
    }
    t.activeTab.value = 'tech-spec'
    expect(t.isReadOnlyTab.value).toBe(false)
  })
})

describe('section gating', () => {
  it('edits and chats on a section only in the stage that owns it', () => {
    const bud = budRef('tech_arch')
    const t = tabsFor(bud)
    t.activeTab.value = 'tech-spec'
    expect(t.currentSection.value).toBe('tech_spec_md')
    expect(t.currentSectionLabel.value).toBe('Tech Spec')
    expect(t.currentSectionEditable.value).toBe(true)
    expect(t.currentSectionChatable.value).toBe(true)

    t.activeTab.value = 'requirements'
    expect(t.currentSectionEditable.value).toBe(false)
    expect(t.currentSectionChatable.value).toBe(false)
    expect(t.editLockTooltip.value).toBe('Move the BUD to BUD to edit this section')
  })

  it('calls Development read-only rather than naming a stage', () => {
    const t = tabsFor(budRef('development'))
    t.activeTab.value = 'development'
    expect(t.currentSectionEditable.value).toBe(false)
    expect(t.editLockTooltip.value).toBe('This section is read-only')
  })

  it('needs a generated design before Design chat opens', () => {
    const bud = budRef('design')
    const t = tabsFor(bud)
    t.activeTab.value = 'design'
    expect(t.currentSectionChatable.value).toBe(false)
    expect(t.needsDesignGeneration.value).toBe(true)

    bud.value = { ...bud.value, designs: [{ id: 'd1' }] } as unknown as BUDDocument
    expect(t.currentSectionChatable.value).toBe(true)
    expect(t.needsDesignGeneration.value).toBe(false)
  })

  it('treats a tab without a section as the requirements section', () => {
    const t = tabsFor(budRef('prod'))
    t.activeTab.value = 'prod'
    expect(t.currentSection.value).toBe('requirements_md')
    expect(t.currentSectionEditable.value).toBe(false)
  })
})
