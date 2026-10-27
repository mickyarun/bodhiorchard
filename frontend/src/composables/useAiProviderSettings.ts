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
 * State for the AI provider settings: the capability table, the saved
 * choice, the edits on screen, save and the connection test. Endpoints:
 * GET /v1/settings/ai/capabilities, GET+PATCH /v1/settings/claude and
 * POST /v1/settings/claude/test.
 */
import { computed, ref, watch } from 'vue'
import type { ProviderCaps } from '@/constants/aiProviders'
import api from '@/services/api'
import {
  authTiles,
  canSaveProvider,
  recommendedMode,
  testOutcome,
  type ProviderTestResult,
} from '@/utils/aiProviderOptions'
import type { ProviderTest } from '@/utils/integrations'

/** Typing a server address probes it; wait for a pause first. */
const MODEL_PROBE_DEBOUNCE_MS = 600
const TEST_TIMEOUT_MS = 120_000

interface SavedSettings {
  provider: string
  auth_mode: string
  has_api_key: boolean
  base_url: string | null
  model: string | null
  thinking: boolean
}

function quietUnlessAuth(label: string, err: unknown): void {
  if ((err as { response?: { status?: number } })?.response?.status !== 401) console.warn(`[ai settings] ${label}`, err)
}

export function useAiProviderSettings() {
  const providers = ref<ProviderCaps[]>([])
  const deploymentMode = ref('')
  const provider = ref('claude')
  const savedProvider = ref('claude')
  const authMode = ref('host')
  const credential = ref('')
  const hasStoredCredential = ref(false)
  const baseUrl = ref('')
  const model = ref('')
  const thinkingChoice = ref<'on' | 'off'>('off')
  const saving = ref(false)
  // The last saved choice, to tell edits apart and to describe the card.
  const saved = ref<SavedSettings | null>(null)
  const test = ref<ProviderTest>('idle')
  const testError = ref('')
  const testVersion = ref('')
  const showInstallHint = ref(false)

  const caps = computed(() => providers.value.find(p => p.provider === provider.value))
  const tiles = computed(() => authTiles(caps.value, deploymentMode.value))
  const mode = computed(() => caps.value?.auth_modes.find(m => m.value === authMode.value))
  const requiresSecret = computed(() => mode.value?.requires_secret ?? false)
  const savedCaps = computed(() => providers.value.find(p => p.provider === savedProvider.value))
  const savedMode = computed(() => savedCaps.value?.auth_modes.find(m => m.value === saved.value?.auth_mode))
  const dirty = computed(() => {
    const s = saved.value
    if (!s) return false
    return (
      provider.value !== s.provider
      || authMode.value !== s.auth_mode
      || baseUrl.value.trim() !== (s.base_url ?? '')
      || model.value !== (s.model ?? '')
      || (thinkingChoice.value === 'on') !== s.thinking
      || credential.value.trim().length > 0
    )
  })
  const canSave = computed(() =>
    dirty.value && canSaveProvider({
      requiresSecret: requiresSecret.value,
      hasStored: hasStoredCredential.value,
      providerChanged: provider.value !== savedProvider.value,
      typed: credential.value,
    }),
  )

  function applySaved(data: SavedSettings): void {
    saved.value = data
    provider.value = data.provider ?? provider.value
    savedProvider.value = provider.value
    authMode.value = data.auth_mode
    hasStoredCredential.value = data.has_api_key
    baseUrl.value = data.base_url ?? ''
    model.value = data.model ?? ''
    thinkingChoice.value = data.thinking ? 'on' : 'off'
  }

  function selectProvider(value: string): void {
    if (provider.value === value) return
    provider.value = value
    credential.value = ''
    const next = providers.value.find(p => p.provider === value)
    if (next) authMode.value = recommendedMode(next, deploymentMode.value)
  }

  // Any change to the choice clears an old test result so the tag always
  // describes what is on screen.
  watch([provider, authMode, credential], () => {
    if (test.value === 'passed' || test.value === 'failed') {
      test.value = 'idle'
      testError.value = ''
      testVersion.value = ''
    }
  })

  // The model list belongs to whichever server the address points at.
  let probeTimer: ReturnType<typeof setTimeout> | undefined
  watch(baseUrl, () => {
    if (!caps.value?.dynamic_models) return
    clearTimeout(probeTimer)
    probeTimer = setTimeout(() => void refreshModels(), MODEL_PROBE_DEBOUNCE_MS)
  })

  async function refreshModels(): Promise<void> {
    try {
      const { data } = await api.get('/v1/settings/ai/capabilities', { params: { base_url: baseUrl.value.trim() || undefined } })
      providers.value = data.providers ?? providers.value
      if (model.value && !(caps.value?.models ?? []).some(m => m.id === model.value)) model.value = ''
    } catch {
      // An unreachable address is normal while typing; the empty list says so.
    }
  }

  async function load(): Promise<void> {
    try {
      const { data } = await api.get('/v1/settings/ai/capabilities')
      providers.value = data.providers ?? []
      deploymentMode.value = data.deployment_mode ?? ''
      provider.value = data.current_provider ?? 'claude'
      savedProvider.value = provider.value
    } catch (err) {
      quietUnlessAuth('failed to load capabilities', err)
    }
    try {
      const { data } = await api.get<SavedSettings>('/v1/settings/claude')
      applySaved(data)
    } catch (err) {
      quietUnlessAuth('failed to load state', err)
    }
    // A stored mode this deployment hides would leave nothing selected.
    if (caps.value && !tiles.value.some(t => t.value === authMode.value)) {
      authMode.value = recommendedMode(caps.value, deploymentMode.value)
    }
  }

  async function save(): Promise<void> {
    saving.value = true
    testError.value = ''
    try {
      const secret = credential.value.trim()
      const sendSecret = requiresSecret.value && secret.length > 0
      const { data } = await api.patch<SavedSettings>('/v1/settings/claude', {
        provider: provider.value,
        auth_mode: authMode.value,
        // Always sent: the backend clears whichever the provider ignores.
        base_url: baseUrl.value.trim(),
        model: model.value,
        thinking: thinkingChoice.value === 'on',
        ...(sendSecret && authMode.value === 'subscription' ? { oauth_token: secret } : {}),
        ...(sendSecret && authMode.value !== 'subscription' ? { api_key: secret } : {}),
      })
      applySaved(data)
      credential.value = ''
      await runTest()
    } catch (err) {
      test.value = 'failed'
      testError.value = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || 'Could not save the AI settings. Try again.'
      console.warn('[ai settings] save failed', err)
    } finally {
      saving.value = false
    }
  }

  function applyTest(data: ProviderTestResult): void {
    const outcome = testOutcome(data)
    test.value = outcome.passed ? 'passed' : 'failed'
    testVersion.value = outcome.passed ? outcome.message : ''
    testError.value = outcome.passed ? '' : outcome.message
    showInstallHint.value = outcome.showInstallHint
  }

  async function runTest(): Promise<void> {
    test.value = 'checking'
    testError.value = ''
    testVersion.value = ''
    showInstallHint.value = false
    try {
      // Test the address on screen, not the last saved one.
      const body = caps.value?.requires_base_url
        ? { base_url: baseUrl.value.trim() || undefined, model: model.value || undefined, thinking: thinkingChoice.value === 'on' }
        : null
      const { data } = await api.post<ProviderTestResult>('/v1/settings/claude/test', body, { timeout: TEST_TIMEOUT_MS })
      applyTest(data)
    } catch (err) {
      test.value = 'failed'
      testError.value = 'Could not reach the server to test the provider.'
      console.warn('[ai settings] test failed', err)
    }
  }

  return {
    providers, deploymentMode, provider, authMode, credential, hasStoredCredential, baseUrl, model, thinkingChoice,
    saving, test, testError, testVersion, showInstallHint,
    caps, tiles, mode, requiresSecret, canSave, dirty, savedCaps, savedMode,
    selectProvider, load, save, runTest,
  }
}
