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
 * POST /v1/settings/claude/test (see useAiProviderTest).
 */
import { computed, ref, watch } from 'vue'
import type { ProviderCaps } from '@/constants/aiProviders'
import api from '@/services/api'
import { authTiles, canSaveProvider, recommendedMode } from '@/utils/aiProviderOptions'
import {
  buildSavePayload,
  hasUnsavedEdits,
  testRequestBody,
  type AiProviderEdits,
  type SavedSettings,
} from '@/utils/aiProviderSettings'
import { useAiProviderTest } from './useAiProviderTest'

/** Typing a server address probes it; wait for a pause first. */
const MODEL_PROBE_DEBOUNCE_MS = 600

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
  // False until load() has the saved choice: a pick made before then would be
  // replaced by it, and Save would send the stored mode instead.
  const loaded = ref(false)
  // The last saved choice, to tell edits apart and to describe the card.
  const saved = ref<SavedSettings | null>(null)

  const caps = computed(() => providers.value.find(p => p.provider === provider.value))
  const tiles = computed(() => authTiles(caps.value, deploymentMode.value))
  const mode = computed(() => caps.value?.auth_modes.find(m => m.value === authMode.value))
  const requiresSecret = computed(() => mode.value?.requires_secret ?? false)
  const savedCaps = computed(() => providers.value.find(p => p.provider === savedProvider.value))
  const savedMode = computed(() => savedCaps.value?.auth_modes.find(m => m.value === saved.value?.auth_mode))

  function edits(): AiProviderEdits {
    return {
      provider: provider.value,
      authMode: authMode.value,
      baseUrl: baseUrl.value,
      model: model.value,
      thinking: thinkingChoice.value === 'on',
      credential: credential.value,
    }
  }

  const dirty = computed(() => hasUnsavedEdits(saved.value, edits()))
  const canSave = computed(() =>
    dirty.value && canSaveProvider({
      requiresSecret: requiresSecret.value,
      hasStored: hasStoredCredential.value,
      providerChanged: provider.value !== savedProvider.value,
      typed: credential.value,
    }),
  )

  const { test, testError, testVersion, showInstallHint, clearOutcome, runTest } = useAiProviderTest(
    () => testRequestBody(caps.value?.requires_base_url ?? false, edits()),
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
  watch([provider, authMode, credential], clearOutcome)

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
    loaded.value = true
  }

  async function save(): Promise<void> {
    saving.value = true
    testError.value = ''
    try {
      const { data } = await api.patch<SavedSettings>('/v1/settings/claude', buildSavePayload(edits(), requiresSecret.value))
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

  return {
    providers, deploymentMode, provider, authMode, credential, hasStoredCredential, baseUrl, model, thinkingChoice,
    loaded, saving, test, testError, testVersion, showInstallHint,
    caps, tiles, mode, requiresSecret, canSave, dirty, savedCaps, savedMode,
    selectProvider, load, save, runTest,
  }
}
