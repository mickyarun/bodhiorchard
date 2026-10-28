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
 * AppMonogram is every avatar in the app: a photo when there is one,
 * initials when there isn't or it fails to load.
 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AppMonogram from '../AppMonogram.vue'

const PHOTO = '/api/v1/employees/avatars/0123456789abcdef0123456789abcdef'

describe('AppMonogram', () => {
  it('shows initials when there is no photo', () => {
    const wrapper = mount(AppMonogram, { props: { name: 'Ada Lovelace' } })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('AL')
  })

  it('shows the photo when there is one', () => {
    const wrapper = mount(AppMonogram, { props: { name: 'Ada Lovelace', src: PHOTO } })
    expect(wrapper.find('img').attributes('src')).toBe(PHOTO)
    expect(wrapper.text()).toBe('')
  })

  it('falls back to initials when the photo fails to load', async () => {
    const wrapper = mount(AppMonogram, { props: { name: 'Ada Lovelace', src: PHOTO } })
    await wrapper.find('img').trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('AL')
  })

  it('tries a new photo after an old one failed', async () => {
    const wrapper = mount(AppMonogram, { props: { name: 'Ada Lovelace', src: PHOTO } })
    await wrapper.find('img').trigger('error')
    await wrapper.setProps({ src: `${PHOTO}x` })
    expect(wrapper.find('img').attributes('src')).toBe(`${PHOTO}x`)
  })

  it('keeps the photo out of the accessibility tree unless labelled', () => {
    const plain = mount(AppMonogram, { props: { name: 'Ada', src: PHOTO } })
    expect(plain.attributes('aria-hidden')).toBe('true')
    expect(plain.find('img').attributes('alt')).toBe('')
    const labelled = mount(AppMonogram, { props: { name: 'Ada', src: PHOTO, label: 'Ada' } })
    expect(labelled.attributes('role')).toBe('img')
    expect(labelled.attributes('aria-label')).toBe('Ada')
  })
})
