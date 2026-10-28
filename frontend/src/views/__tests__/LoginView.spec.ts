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
 * The sign-in page: it looks up the workspace on arrival, sends an
 * unfinished install to the wizard, signs in against that workspace, and
 * shows why a sign-in failed. The real auth store runs against a mocked
 * API; Vuetify parts are stubbed down to plain form controls.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => router }))
vi.mock('@/services/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import LoginView from '@/views/LoginView.vue'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)
const ENGINEER = { id: 'u1', permissions: ['workspace:engineering'], character_model: 'knight' }

const field = {
  props: ['modelValue', 'label'],
  emits: ['update:modelValue'],
  template:
    '<label>{{ label }}<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" /></label>',
}
const stubs = {
  AuthShell: { template: '<main><slot /><slot name="note" /></main>' },
  AppCallout: { template: '<div class="callout" role="alert"><slot /></div>' },
  PasswordField: field,
  'v-text-field': field,
  // Declared emit: otherwise the listener also falls through to the native form.
  'v-form': { emits: ['submit'], template: '<form @submit.prevent="$emit(\'submit\', $event)"><slot /></form>' },
  'v-btn': { props: ['disabled'], template: '<button type="submit" :disabled="disabled"><slot /></button>' },
}

function setupStatus(data: Record<string, unknown>): void {
  get.mockImplementation(async (url: string) => {
    if (url === '/setup/status') return { data }
    if (url === '/v1/auth/me') return { data: ENGINEER }
    throw new Error(`unexpected GET ${url}`)
  })
}

async function mountLogin() {
  const wrapper = mount(LoginView, { global: { stubs } })
  await flushPromises()
  return wrapper
}

async function signIn(wrapper: Awaited<ReturnType<typeof mountLogin>>, email: string, password: string) {
  const inputs = wrapper.findAll('input')
  await inputs[0].setValue(email)
  await inputs[1].setValue(password)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  sessionStorage.clear()
  get.mockReset()
  post.mockReset()
  router.push.mockReset()
  router.replace.mockReset()
})

describe('LoginView', () => {
  it('sends an install that has not finished setup to the wizard', async () => {
    setupStatus({ is_setup_complete: false })
    await mountLogin()
    expect(router.replace).toHaveBeenCalledWith({ name: 'setup' })
  })

  it("signs in against the workspace's slug and goes on to the engineer's home", async () => {
    setupStatus({ is_setup_complete: true, org_slug: 'acme' })
    post.mockResolvedValue({ data: { access_token: 'a1', refresh_token: 'r1' } })
    const wrapper = await mountLogin()

    await signIn(wrapper, '  ana@example.com ', 'secret-pass')

    expect(post).toHaveBeenCalledWith('/v1/auth/login', {
      email: 'ana@example.com', password: 'secret-pass', org_slug: 'acme',
    })
    expect(router.push).toHaveBeenCalledWith({ name: 'dashboard' })
    expect(wrapper.find('.callout').exists()).toBe(false)
  })

  it('sends someone with a temporary password to change it first', async () => {
    setupStatus({ is_setup_complete: true, org_slug: 'acme' })
    post.mockResolvedValue({ data: { access_token: 'a1', must_change_password: true } })
    const wrapper = await mountLogin()
    await signIn(wrapper, 'ana@example.com', 'temp-pass')
    expect(router.push).toHaveBeenCalledWith({ name: 'change-password' })
  })

  it('shows why a sign-in failed and stays on the page', async () => {
    setupStatus({ is_setup_complete: true, org_slug: 'acme' })
    post.mockRejectedValue(Object.assign(new Error('401'), { response: { status: 401, data: {} } }))
    const wrapper = await mountLogin()
    await signIn(wrapper, 'ana@example.com', 'wrong')
    expect(wrapper.find('.callout').text()).toBe('Invalid email or password.')
    expect(router.push).not.toHaveBeenCalled()
  })

  it('says the server is unreachable only once someone tries, and recovers when it is back', async () => {
    get.mockRejectedValueOnce(new Error('Network Error'))
    const wrapper = await mountLogin()
    expect(wrapper.find('.callout').exists()).toBe(false)

    get.mockRejectedValueOnce(new Error('Network Error'))
    await signIn(wrapper, 'ana@example.com', 'secret-pass')
    expect(wrapper.find('.callout').text()).toContain("Can't reach Glideship right now.")
    expect(post).not.toHaveBeenCalled()

    setupStatus({ is_setup_complete: true, org_slug: 'acme' })
    post.mockResolvedValue({ data: { access_token: 'a1' } })
    await signIn(wrapper, 'ana@example.com', 'secret-pass')
    expect(post).toHaveBeenCalledOnce()
    expect(wrapper.find('.callout').exists()).toBe(false)
    expect(router.push).toHaveBeenCalledOnce()
  })

  it('keeps the button disabled and sends nothing until both fields are filled', async () => {
    setupStatus({ is_setup_complete: true, org_slug: 'acme' })
    const wrapper = await mountLogin()
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
    await signIn(wrapper, '   ', 'secret-pass')
    expect(post).not.toHaveBeenCalled()
    await signIn(wrapper, 'ana@example.com', '')
    expect(post).not.toHaveBeenCalled()
  })

  it('does not greet a new visit with the last error', async () => {
    setupStatus({ is_setup_complete: true, org_slug: 'acme' })
    useAuthStore().loginError = 'Invalid email or password.'
    const wrapper = await mountLogin()
    expect(wrapper.find('.callout').exists()).toBe(false)
  })
})
