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

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import BUDSectionDiffDrawer from '../BUDSectionDiffDrawer.vue'

// ``vi.mock`` is hoisted above the imports, so the spy has to be created
// inside ``vi.hoisted`` to exist by the time the factory runs.
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/services/api', () => ({
  default: { get: apiGet, post: vi.fn() },
}))

const BUD_ID = 'bud-1'

// ``GET /v1/buds/{id}/designs`` responds with a BARE ARRAY
// (``response_model=list[BUDDesignRead]`` in bud_designs.py), not an
// envelope. The drawer used to read ``data.designs``, which threw
// "Cannot read properties of undefined (reading 'find')" and left the
// Design-section history permanently broken. Shape the fixture exactly
// like the endpoint so an envelope regression fails here.
const DESIGNS_RESPONSE = [
  {
    id: 'd-repo',
    bud_id: BUD_ID,
    repo_id: 'repo-1',
    repo_name: 'web',
    design_html: '<p>per-repo</p>',
    notes: null,
    status: 'ready',
    job_id: null,
    created_at: '2026-08-17T10:00:00Z',
    updated_at: '2026-08-17T10:00:00Z',
  },
  {
    id: 'd-bud',
    bud_id: BUD_ID,
    repo_id: null,
    repo_name: null,
    design_html: '<p>current</p>',
    notes: null,
    status: 'ready',
    job_id: null,
    created_at: '2026-08-17T11:00:00Z',
    updated_at: '2026-08-17T11:00:00Z',
  },
]

const DESIGN_VERSION = {
  id: 'v-1',
  phase: 'design',
  version_no: 1,
  source: 'ui',
  edited_by: null,
  mcp_token_id: null,
  reason: null,
  edited_at: '2026-08-17T09:00:00Z',
}

// Design snapshots key off the ``__design_html`` sentinel because design
// content lives in bud_designs, not bud_documents.
const DESIGN_VERSION_DETAIL = {
  ...DESIGN_VERSION,
  snapshot: { __design_html: '<p>old</p>' },
}

// Pass-through stubs: Vuetify wrappers render their default slot so the
// drawer body is reachable, leaf components stay inert.
const PASSTHROUGH = { template: '<div><slot /></div>' }
const VUETIFY_STUBS = {
  'v-navigation-drawer': PASSTHROUGH,
  'v-dialog': PASSTHROUGH,
  'v-card': PASSTHROUGH,
  'v-card-actions': PASSTHROUGH,
  'v-chip': PASSTHROUGH,
  'v-tooltip': PASSTHROUGH,
  'v-snackbar': PASSTHROUGH,
  'v-icon': true,
  'v-btn': true,
  'v-spacer': true,
  'v-progress-circular': true,
}

function mountDrawer(section: 'design' | 'requirements') {
  return mount(BUDSectionDiffDrawer, {
    global: { stubs: VUETIFY_STUBS },
    props: { modelValue: true, budId: BUD_ID, budStatus: 'design', section },
  })
}

describe('BUDSectionDiffDrawer — current-content baseline', () => {
  beforeEach(() => {
    apiGet.mockReset()
  })

  function stubApi(designs: unknown[], versions: unknown[] = [DESIGN_VERSION]) {
    apiGet.mockImplementation((url: string) => {
      if (url.endsWith('/designs')) return Promise.resolve({ data: designs })
      if (url.endsWith('/versions')) return Promise.resolve({ data: versions })
      if (url.includes('/versions/')) return Promise.resolve({ data: DESIGN_VERSION_DETAIL })
      return Promise.resolve({ data: {} })
    })
  }

  // Selecting the only rail entry renders the diff of that snapshot
  // against whatever ``fetchCurrentContent`` resolved to — which is what
  // makes the baseline observable from the DOM.
  async function openFirstVersion(wrapper: ReturnType<typeof mountDrawer>) {
    await wrapper.findAll('.diff-rail__item')[0].trigger('click')
    await flushPromises()
    return wrapper.findAll('.diff-line').map((n) => n.text().replace(/\s+/g, ' ').trim())
  }

  it('diffs against the BUD-level design row from the bare designs array', async () => {
    stubApi(DESIGNS_RESPONSE)
    const wrapper = mountDrawer('design')
    await flushPromises()

    // The old ``data.designs.find`` threw here and the catch surfaced the
    // raw TypeError to the user as a red toast.
    expect(wrapper.text()).not.toContain('Cannot read properties')
    expect(apiGet).toHaveBeenCalledWith(`/v1/buds/${BUD_ID}/designs`)

    // Baseline resolved to the BUD-level row, not the per-repo one.
    const lines = await openFirstVersion(wrapper)
    expect(lines).toContain('−<p>old</p>')
    expect(lines).toContain('+<p>current</p>')
    expect(lines.join(' ')).not.toContain('per-repo')
  })

  it('treats a BUD with only per-repo designs as an empty baseline', async () => {
    stubApi([DESIGNS_RESPONSE[0]])
    const wrapper = mountDrawer('design')
    await flushPromises()

    // An empty baseline must come from an actual miss on ``repo_id == null``,
    // not from the catch block swallowing a shape error.
    expect(wrapper.text()).not.toContain('Cannot read properties')

    const lines = await openFirstVersion(wrapper)
    expect(lines).toContain('−<p>old</p>')
    expect(lines.some((l) => l.startsWith('+'))).toBe(false)
  })

  it('scopes the version rail to the section phase', async () => {
    stubApi(DESIGNS_RESPONSE, [
      DESIGN_VERSION,
      { ...DESIGN_VERSION, id: 'v-2', phase: 'bud', version_no: 2 },
    ])
    const wrapper = mountDrawer('design')
    await flushPromises()

    const rail = wrapper.findAll('.diff-rail__item')
    expect(rail).toHaveLength(1)
    expect(rail[0].text()).toContain('v1')
  })
})
