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
 * Component tests for the shared attachment tile.
 *
 * This tile backs two surfaces — bug attachments and QA evidence (via
 * the ``EvidenceTile`` adapter) — so the branches asserted here are a
 * shared contract, not one screen's details. Vuetify components are
 * stubbed: the interesting behaviour is which branch renders, what is
 * fetched, and what is emitted, none of which needs real Vuetify.
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiGet = vi.fn()
vi.mock('@/services/api', () => ({ default: { get: apiGet } }))

const AttachmentTile = (await import('./AttachmentTile.vue')).default

/** Stub the Vuetify pieces the tile renders, keeping slot content. */
const global = {
  stubs: {
    'v-icon': { props: ['icon'], template: '<i class="v-icon" :data-icon="icon"><slot /></i>' },
    'v-progress-circular': true,
    // No `props` declaration: anything declared would be consumed as a
    // prop and stripped from `$attrs`, so `aria-label` would never reach
    // the DOM and the copy assertions below would silently pass on
    // undefined.
    'v-btn': {
      inheritAttrs: false,
      template: '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>',
    },
    'v-tooltip': { template: '<span class="v-tooltip"><slot /></span>' },
  },
}

type TileProps = InstanceType<typeof AttachmentTile>['$props']

function mountTile(props: TileProps) {
  return mount(AttachmentTile, { props, global })
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue({ data: new Blob(['bytes']) })
  // jsdom has no object-URL implementation.
  URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  URL.revokeObjectURL = vi.fn()
  // The tile logs failures deliberately (see its catch blocks); silence
  // that here so a passing run has clean output.
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('source branch', () => {
  it('fetches an image through the API client and renders a thumbnail', async () => {
    const wrapper = mountTile({
      filename: 'shot.png',
      mimeType: 'image/png',
      fetchPath: '/v1/bugs/abc/attachments/1',
    })
    await flushPromises()

    // The download route is Bearer-gated, so the bytes must come through
    // the API client (whose interceptor attaches the JWT), never a bare
    // <img src>.
    expect(apiGet).toHaveBeenCalledWith(
      '/v1/bugs/abc/attachments/1',
      expect.objectContaining({ responseType: 'blob' }),
    )
    expect(wrapper.find('img').attributes('src')).toBe('blob:mock-url')
  })

  it('gives blob requests a longer budget than the client default', async () => {
    mountTile({ filename: 'shot.png', mimeType: 'image/png', fetchPath: '/p' })
    await flushPromises()

    // 30s (the client default) would abort a large attachment mid-transfer
    // and surface as a bogus "couldn't load preview".
    const config = apiGet.mock.calls[0][1] as { timeout: number }
    expect(config.timeout).toBeGreaterThan(30_000)
  })

  it('renders an icon and fetches nothing for a non-image', async () => {
    const wrapper = mountTile({
      filename: 'report.pdf',
      mimeType: 'application/pdf',
      fetchPath: '/v1/bugs/abc/attachments/2',
    })
    await flushPromises()

    expect(apiGet).not.toHaveBeenCalled()
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('[data-icon="mdi-file-pdf-box"]').exists()).toBe(true)
  })

  it('previews a staged file without any network call', async () => {
    const file = new File(['x'], 'staged.png', { type: 'image/png' })
    const wrapper = mountTile({ filename: 'staged.png', mimeType: 'image/png', file })
    await flushPromises()

    // Files picked in the create dialog aren't uploaded yet — there is
    // nothing to fetch, and asking the API for one would 404.
    expect(apiGet).not.toHaveBeenCalled()
    expect(URL.createObjectURL).toHaveBeenCalledWith(file)
    expect(wrapper.find('img').exists()).toBe(true)
  })
})

/**
 * A rejection shaped like the real thing: axios attaches the parsed
 * body on `response.data` (the client's interceptor normalises the Blob
 * a `responseType: 'blob'` request would otherwise leave there), and
 * `message` stays the generic status text. A hand-rolled `new
 * Error(detail)` would pass assertions that production never satisfies.
 */
function axiosRejection(status: number, detail: string) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail } },
  })
}

describe('failure handling', () => {
  it("surfaces the backend's detail, not axios's generic status text", async () => {
    // The QA evidence route answers 404 "Evidence not found" and can
    // also return a storage-misconfiguration message; both used to be
    // shown verbatim and must keep reaching the user.
    apiGet.mockRejectedValue(axiosRejection(404, 'Evidence not found'))
    const wrapper = mountTile({ filename: 'gone.png', mimeType: 'image/png', fetchPath: '/p' })
    await flushPromises()

    const message = wrapper.emitted('error')?.[0][0] as string
    expect(message).toContain('gone.png')
    expect(message).toContain('Evidence not found')
    expect(message).not.toContain('status code')
  })

  it('reports a connection problem plainly when nothing came back', async () => {
    apiGet.mockRejectedValue(new Error('Network Error'))
    const wrapper = mountTile({ filename: 'gone.png', mimeType: 'image/png', fetchPath: '/p' })
    await flushPromises()

    const message = wrapper.emitted('error')?.[0][0] as string
    expect(message).toBe(`Couldn't load a preview for "gone.png" — check your connection.`)
  })

  it('renders the broken-image icon rather than a permanent spinner', async () => {
    apiGet.mockRejectedValue(axiosRejection(404, 'Evidence not found'))
    const wrapper = mountTile({ filename: 'gone.png', mimeType: 'image/png', fetchPath: '/p' })
    await flushPromises()

    expect(wrapper.find('[data-icon="mdi-image-broken-variant"]').exists()).toBe(true)
    expect(wrapper.find('v-progress-circular-stub').exists()).toBe(false)
  })
})

describe('download', () => {
  it('names the saved file after the attachment', async () => {
    const clicks: HTMLAnchorElement[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicks.push(this)
    })

    const wrapper = mountTile({
      filename: 'quarterly report.pdf',
      mimeType: 'application/pdf',
      fetchPath: '/p',
    })
    await wrapper.find('.tile-file').trigger('click')
    await flushPromises()

    // The whole point of fetch-then-click: the browser can't send the
    // bearer token on a plain <a href>, so the name has to come from us.
    expect(clicks).toHaveLength(1)
    expect(clicks[0].download).toBe('quarterly report.pdf')
    expect(clicks[0].href).toBe('blob:mock-url')
  })
})

describe('preview', () => {
  it('emits the object URL when an image tile is clicked', async () => {
    const wrapper = mountTile({ filename: 'shot.png', mimeType: 'image/png', fetchPath: '/p' })
    await flushPromises()
    await wrapper.find('.tile-image').trigger('click')

    expect(wrapper.emitted('preview')?.[0]).toEqual(['blob:mock-url'])
  })
})

describe('remove affordance', () => {
  it('defaults to generic copy naming the file', () => {
    const wrapper = mountTile({ filename: 'shot.png', mimeType: 'image/png', file: null })
    expect(wrapper.find('.remove-btn').attributes('aria-label')).toBe('Remove shot.png')
    expect(wrapper.find('.v-tooltip').text()).toBe('Remove')
  })

  it('honours overridden copy so QA evidence keeps its own wording', () => {
    // EvidenceTile passes these; adopting the shared tile must not
    // silently reword an existing surface.
    const wrapper = mountTile({
      filename: 'shot.png',
      mimeType: 'image/png',
      removeLabel: 'Delete evidence. Upload a replacement after deleting.',
      removeTooltip: 'Delete, then re-upload to replace',
    })
    expect(wrapper.find('.remove-btn').attributes('aria-label')).toBe(
      'Delete evidence. Upload a replacement after deleting.',
    )
    expect(wrapper.find('.v-tooltip').text()).toBe('Delete, then re-upload to replace')
  })

  it('is hidden when the tile is read-only', () => {
    const wrapper = mountTile({
      filename: 'shot.png',
      mimeType: 'image/png',
      removable: false,
    })
    expect(wrapper.find('.remove-btn').exists()).toBe(false)
  })
})

describe('object URL lifecycle', () => {
  it('revokes the object URL on unmount', async () => {
    const wrapper = mountTile({ filename: 'shot.png', mimeType: 'image/png', fetchPath: '/p' })
    await flushPromises()
    wrapper.unmount()

    // Not revoking leaks the blob for the page's lifetime; a bug with
    // ten screenshots reopened repeatedly adds up.
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })
})
