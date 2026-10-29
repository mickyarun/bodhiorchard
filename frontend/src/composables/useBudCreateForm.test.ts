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

/** The New BUD form's stage-agent switches, while the skills are still loading. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, reactive, ref } from 'vue'

const h = vi.hoisted(() => ({
  push: vi.fn(),
  createBUD: vi.fn(),
  release: (): void => undefined,
}))
const skills = reactive({
  skills: [] as { id: string; agentType: string; isDefault: boolean; name: string }[],
  loading: false,
  fetchSkills: vi.fn(),
})
vi.mock('vue-router', () => ({ useRouter: () => ({ push: h.push }) }))
vi.mock('@/stores/bud', () => ({ useBUDStore: () => ({ createBUD: h.createBUD, error: '' }) }))
vi.mock('@/stores/agentSkills', () => ({ useAgentSkillsStore: () => skills }))

import { CREATE_STAGES, useBudCreateForm } from '@/composables/useBudCreateForm'

/** Skills arrive only when the test calls `h.release()`. */
function slowSkills(): void {
  skills.fetchSkills.mockImplementation(() => {
    skills.loading = true
    return new Promise<void>(resolve => {
      h.release = () => {
        skills.skills = CREATE_STAGES.map(s => ({ id: `${s.value}-skill`, agentType: s.agentType, isDefault: true, name: 'Default' }))
        skills.loading = false
        resolve()
      }
    })
  })
}

const flush = async (): Promise<void> => {
  for (let i = 0; i < 3; i += 1) await nextTick()
}

beforeEach(() => {
  vi.clearAllMocks()
  skills.skills = []
  skills.loading = false
  h.createBUD.mockResolvedValue({ id: 'bud-1' })
  slowSkills()
})

describe('useBudCreateForm stage agents', () => {
  it('shows every agent on as soon as the dialog opens, before the skills load', async () => {
    const open = ref(false)
    const form = useBudCreateForm(open)
    open.value = true
    await flush()
    for (const stage of CREATE_STAGES) expect(form.autoGenerate.value[stage.value]).toBe(true)
  })

  it('keeps an agent the person switched off while the skills were loading off', async () => {
    const open = ref(false)
    const form = useBudCreateForm(open)
    open.value = true
    await flush()
    form.autoGenerate.value.bud = false
    h.release()
    await flush()

    expect(form.autoGenerate.value.bud).toBe(false)
    expect(form.stageSkillPicks.value.bud).toBe('bud-skill')
    form.title.value = 'Passkey sign-in'
    await form.submit()
    const phases = h.createBUD.mock.calls[0][3] as Record<string, boolean>
    expect(phases).toEqual({ bud: false, design: true, tech_arch: true, testing: true, closed: true })
  })
})
