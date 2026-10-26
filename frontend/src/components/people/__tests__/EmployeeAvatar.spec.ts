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
 * EmployeeAvatar: photo vs initials, the edit affordances, and the two
 * bugs it once had — a camera click that opened the file dialog *and* the
 * menu, and a removed photo that stayed on screen.
 *
 * `.spec.ts` for jsdom (File, FormData, DOM events).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'

const apiPost = vi.fn()
const apiDelete = vi.fn()
vi.mock('@/services/api', () => ({ default: { post: apiPost, delete: apiDelete } }))

const { default: EmployeeAvatar } = await import('../EmployeeAvatar.vue')

/** Minimal Vuetify stand-ins that keep slots, attrs and events. */
const passthrough = (tag: string) =>
  defineComponent({
    inheritAttrs: false,
    setup(_, { slots, attrs }) {
      return () => h(tag, { ...attrs }, slots.default?.())
    },
  })

const VImg = defineComponent({
  props: { src: String, alt: String },
  emits: ['error'],
  setup(props, { emit }) {
    return () => h('img', { src: props.src, alt: props.alt, onError: () => emit('error') })
  },
})

const VBtn = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs }) {
    return () => h('button', { ...attrs, type: 'button' })
  },
})

// v-menu: renders the activator with props that open it, and the content
// only once opened — enough to tell "menu opened" from "dialog opened".
const VMenu = defineComponent({
  data: () => ({ open: false }),
  render() {
    const activator = this.$slots.activator?.({
      props: { onClick: () => (this.open = true), 'data-menu-activator': 'true' },
    })
    return h('div', [activator, this.open ? h('div', { class: 'menu' }, this.$slots.default?.()) : null])
  },
})

const VListItem = defineComponent({
  props: { title: String },
  emits: ['click'],
  setup(props, { emit }) {
    return () => h('div', { class: 'menu-item', onClick: () => emit('click') }, props.title)
  },
})

const STUBS = {
  'v-avatar': passthrough('div'),
  'v-img': VImg,
  'v-btn': VBtn,
  'v-menu': VMenu,
  'v-list': passthrough('div'),
  'v-list-item': VListItem,
}

const PHOTO = '/api/v1/employees/avatars/0123456789abcdef0123456789abcdef'

function mountAvatar(props: Record<string, unknown> = {}) {
  return mount(EmployeeAvatar, {
    global: { stubs: STUBS },
    props: { userId: 'u1', name: 'Ada Lovelace', avatarUrl: null, ...props },
  })
}

let fileDialogs = 0
const realClick = HTMLInputElement.prototype.click

beforeEach(() => {
  fileDialogs = 0
  HTMLInputElement.prototype.click = function (this: HTMLInputElement) {
    if (this.type === 'file') fileDialogs++
    else realClick.call(this)
  }
  apiPost.mockReset()
  apiDelete.mockReset()
})

afterEach(() => {
  HTMLInputElement.prototype.click = realClick
})

describe('EmployeeAvatar', () => {
  it('shows initials when there is no photo', () => {
    const wrapper = mountAvatar()
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('AL')
  })

  it('shows the photo, and falls back to initials if it fails to load', async () => {
    const wrapper = mountAvatar({ avatarUrl: PHOTO })
    expect(wrapper.find('img').attributes('src')).toBe(PHOTO)
    await wrapper.find('img').trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('AL')
  })

  it('tries again when the photo URL changes after a failed load', async () => {
    const wrapper = mountAvatar({ avatarUrl: PHOTO })
    await wrapper.find('img').trigger('error')
    await wrapper.setProps({ avatarUrl: `${PHOTO}x` })
    expect(wrapper.find('img').attributes('src')).toBe(`${PHOTO}x`)
  })

  it('offers no edit button when not editable', () => {
    expect(mountAvatar({ avatarUrl: PHOTO }).find('button').exists()).toBe(false)
  })

  it('opens the file picker straight away when there is no photo yet', async () => {
    const wrapper = mountAvatar({ editable: true })
    await wrapper.find('button').trigger('click')
    expect(fileDialogs).toBe(1)
  })

  it('with a photo, the camera opens only the menu — never the file dialog too', async () => {
    const wrapper = mountAvatar({ editable: true, avatarUrl: PHOTO })
    const camera = wrapper.find('button')
    expect(camera.attributes('data-menu-activator')).toBe('true')
    await camera.trigger('click')
    expect(fileDialogs).toBe(0)
    expect(wrapper.findAll('.menu-item').map(i => i.text())).toEqual([
      'Replace photo',
      'Remove photo',
    ])
  })

  it('removing the photo shows initials immediately', async () => {
    apiDelete.mockResolvedValue({ data: { avatar_url: null } })
    const wrapper = mountAvatar({ editable: true, avatarUrl: PHOTO })
    await wrapper.find('button').trigger('click')
    await wrapper.findAll('.menu-item')[1].trigger('click')
    await new Promise(r => setTimeout(r))
    expect(apiDelete).toHaveBeenCalledWith('/v1/employees/u1/avatar')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('AL')
    expect(wrapper.emitted('updated')?.[0]).toEqual([null])
  })

  it('refuses files over 20 MB before uploading', async () => {
    const wrapper = mountAvatar({ editable: true })
    const input = wrapper.find('input[type="file"]')
    const big = new File(['x'], 'huge.jpg', { type: 'image/jpeg' })
    Object.defineProperty(big, 'size', { value: 21 * 1024 * 1024 })
    Object.defineProperty(input.element, 'files', { value: [big] })
    await input.trigger('change')
    expect(apiPost).not.toHaveBeenCalled()
    expect(wrapper.emitted('error')?.[0]?.[0]).toContain('20 MB')
  })

  it('uploads a picked file and shows the new photo', async () => {
    apiPost.mockResolvedValue({ data: { avatar_url: PHOTO } })
    const wrapper = mountAvatar({ editable: true })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['img'], 'me.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await new Promise(r => setTimeout(r))
    expect(apiPost.mock.calls[0][0]).toBe('/v1/employees/u1/avatar')
    expect(wrapper.find('img').attributes('src')).toBe(PHOTO)
  })
})
