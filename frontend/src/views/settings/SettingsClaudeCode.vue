<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<template>
  <v-card class="pa-5 settings-card claude-card" color="surface">
    <div class="d-flex align-center ga-3 mb-1">
      <v-avatar size="36" color="surface-variant" rounded="lg">
        <v-icon icon="mdi-console" size="22" />
      </v-avatar>
      <div class="flex-grow-1">
        <div class="text-body-1 font-weight-medium">AI Provider</div>
        <div class="text-caption text-medium-emphasis">
          Choose which agent CLI runs codebase-aware tasks and how the backend authenticates with it.
        </div>
      </div>
      <v-chip
        v-if="deploymentMode"
        :color="deploymentMode === 'docker' ? 'info' : 'success'"
        variant="tonal" size="small"
        :prepend-icon="deploymentMode === 'docker' ? 'mdi-docker' : 'mdi-laptop'"
      >
        {{ deploymentMode === 'docker' ? 'Full Docker' : 'Hybrid' }}
      </v-chip>
      <v-chip
        v-if="claudeStatus === 'passed'"
        color="success" variant="flat" size="small"
        prepend-icon="mdi-check-circle-outline"
      >
        Connected
      </v-chip>
      <v-chip
        v-else-if="claudeStatus === 'failed'"
        color="error" variant="flat" size="small"
        prepend-icon="mdi-alert-circle-outline"
      >
        Not Available
      </v-chip>
    </div>

    <v-divider class="my-4" />

    <div class="text-body-2 font-weight-medium mb-3">Provider</div>
    <div role="radiogroup" aria-label="AI provider" class="auth-mode-tiles mb-4">
      <button
        v-for="prov in providerOptions"
        :key="prov.value"
        type="button"
        role="radio"
        :aria-checked="provider === prov.value"
        class="auth-tile"
        :class="{ 'auth-tile--active': provider === prov.value }"
        @click="selectProvider(prov.value)"
        @keydown.space.prevent="selectProvider(prov.value)"
      >
        <div class="auth-tile__indicator">
          <v-icon
            :icon="provider === prov.value ? 'mdi-radiobox-marked' : 'mdi-radiobox-blank'"
            :color="provider === prov.value ? 'primary' : undefined"
            size="20"
          />
        </div>
        <div class="auth-tile__body">
          <div class="auth-tile__header">
            <v-icon :icon="prov.icon" size="18" class="auth-tile__icon" />
            <span class="text-body-2 font-weight-medium">{{ prov.title }}</span>
          </div>
          <div class="text-caption text-medium-emphasis auth-tile__desc">
            Runs via the <code>{{ prov.cli }}</code> CLI.
          </div>
        </div>
      </button>
    </div>

    <div class="text-body-2 font-weight-medium mb-3">Authentication mode</div>
    <div role="radiogroup" aria-label="Authentication mode" class="auth-mode-tiles mb-4">
      <button
        v-for="opt in authOptions"
        :key="opt.value"
        type="button"
        role="radio"
        :aria-checked="authMode === opt.value"
        class="auth-tile"
        :class="{ 'auth-tile--active': authMode === opt.value }"
        @click="authMode = opt.value"
        @keydown.space.prevent="authMode = opt.value"
      >
        <div class="auth-tile__indicator">
          <v-icon
            :icon="authMode === opt.value ? 'mdi-radiobox-marked' : 'mdi-radiobox-blank'"
            :color="authMode === opt.value ? 'primary' : undefined"
            size="20"
          />
        </div>
        <div class="auth-tile__body">
          <div class="auth-tile__header">
            <v-icon :icon="opt.icon" size="18" class="auth-tile__icon" />
            <span class="text-body-2 font-weight-medium">{{ opt.title }}</span>
            <v-chip
              v-if="opt.badge"
              size="x-small" variant="tonal" color="primary" class="auth-tile__badge"
            >
              {{ opt.badge }}
            </v-chip>
          </div>
          <div class="text-caption text-medium-emphasis auth-tile__desc">
            {{ opt.description }}
          </div>
        </div>
      </button>
    </div>

    <v-expand-transition>
      <div v-if="requiresSecret" class="mb-3">
        <v-text-field
          v-model="credential"
          :label="credentialLabel"
          :placeholder="hasStoredCredential ? '•••••••••••••••• (stored — leave blank to keep)' : credentialPlaceholder"
          type="password"
          variant="outlined"
          density="compact"
          autocomplete="off"
          hide-details
          class="mb-2"
        />
        <div v-if="docsUrl" class="text-caption text-medium-emphasis">
          Credentials docs:
          <a :href="docsUrl" target="_blank" rel="noopener">{{ docsUrl }}</a>.
        </div>
      </div>
    </v-expand-transition>

    <div class="d-flex ga-2 mt-2 flex-wrap">
      <v-btn
        color="primary" variant="flat" prepend-icon="mdi-content-save"
        :loading="saving" :disabled="!canSave" @click="save"
      >
        Save
      </v-btn>
      <v-btn
        variant="tonal" prepend-icon="mdi-connection"
        :loading="claudeStatus === 'checking'" @click="checkConnection"
      >
        {{ claudeStatus === 'idle' ? 'Test connection' : 'Retest' }}
      </v-btn>
    </div>

    <v-expand-transition>
      <div v-if="claudeStatus === 'failed'" class="mt-3">
        <v-alert type="warning" variant="tonal" density="compact">
          <div class="text-body-2 mb-2">{{ claudeError }}</div>
          <div v-if="showInstallHint && installHint" class="text-caption">
            <code>{{ installHint }}</code>
          </div>
        </v-alert>
      </div>
    </v-expand-transition>

    <v-expand-transition>
      <div v-if="claudeStatus === 'passed' && claudeVersion" class="mt-3">
        <div class="text-caption text-medium-emphasis">
          <v-icon icon="mdi-information-outline" size="14" class="mr-1" />
          {{ claudeVersion }}
        </div>
      </div>
    </v-expand-transition>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'

type Status = 'idle' | 'checking' | 'passed' | 'failed'

interface AuthModeSpec { value: string; label: string; requires_secret: boolean }
interface ProviderCaps {
  provider: string
  cli: string
  auth_modes: AuthModeSpec[]
  install_hint: string
  docs_url: string
}

const PROVIDER_META: Record<string, { title: string; icon: string }> = {
  claude: { title: 'Claude', icon: 'mdi-robot-happy-outline' },
  copilot: { title: 'GitHub Copilot', icon: 'mdi-github' },
  codex: { title: 'OpenAI Codex', icon: 'mdi-alpha-c-box-outline' },
}
const MODE_META: Record<string, { icon: string }> = {
  host: { icon: 'mdi-laptop' },
  api_key: { icon: 'mdi-key-variant' },
  subscription: { icon: 'mdi-account-key-outline' },
}

const providersCaps = ref<ProviderCaps[]>([])
const deploymentMode = ref<string>('')
const provider = ref<string>('claude')
const loadedProvider = ref<string>('claude')
const authMode = ref<string>('host')
const credential = ref('')
const hasStoredCredential = ref(false)
const saving = ref(false)

const claudeStatus = ref<Status>('idle')
const claudeError = ref('')
const claudeVersion = ref('')
const showInstallHint = ref(false)

const currentCaps = computed<ProviderCaps | undefined>(() =>
  providersCaps.value.find((p) => p.provider === provider.value),
)

const providerOptions = computed(() =>
  providersCaps.value.map((p) => ({
    value: p.provider,
    title: PROVIDER_META[p.provider]?.title ?? p.provider,
    icon: PROVIDER_META[p.provider]?.icon ?? 'mdi-robot',
    cli: p.cli,
  })),
)

function modeDescription(mode: AuthModeSpec): string {
  if (!mode.requires_secret) {
    return 'Inherits the host login / process environment. Nothing is stored in the database.'
  }
  if (mode.value === 'subscription') {
    return 'Paste an OAuth token from `claude setup-token`. Uses your Claude plan, stored encrypted.'
  }
  return `Paste a ${mode.label}. Stored encrypted (Fernet AES-128) and applied to every agent run.`
}

const authOptions = computed(() => {
  const caps = currentCaps.value
  if (!caps) return []
  // Full Docker can't reach a host login session — hide the host tile there.
  const modes = caps.auth_modes.filter(
    (m) => !(deploymentMode.value === 'docker' && m.value === 'host'),
  )
  const recommended = recommendedMode(caps)
  return modes.map((m) => ({
    value: m.value,
    title: m.label,
    icon: MODE_META[m.value]?.icon ?? 'mdi-key',
    description: modeDescription(m),
    badge: m.value === recommended ? 'Recommended' : undefined,
  }))
})

function recommendedMode(caps: ProviderCaps): string {
  if (deploymentMode.value === 'docker') {
    const cred = caps.auth_modes.find((m) => m.requires_secret)
    return cred?.value ?? caps.auth_modes[0]?.value ?? 'api_key'
  }
  const host = caps.auth_modes.find((m) => m.value === 'host')
  return host?.value ?? caps.auth_modes[0]?.value ?? 'host'
}

const selectedMode = computed<AuthModeSpec | undefined>(() =>
  currentCaps.value?.auth_modes.find((m) => m.value === authMode.value),
)
const requiresSecret = computed(() => selectedMode.value?.requires_secret ?? false)
const credentialLabel = computed(() => selectedMode.value?.label ?? 'Credential')
const credentialPlaceholder = computed(() => {
  if (provider.value === 'copilot') return 'ghp_…'
  if (provider.value === 'codex') return 'sk-…'
  return authMode.value === 'subscription' ? 'sk-ant-oat…' : 'sk-ant-…'
})
const docsUrl = computed(() => currentCaps.value?.docs_url ?? '')
const installHint = computed(() => currentCaps.value?.install_hint ?? '')

const canSave = computed(() => {
  if (!requiresSecret.value) return true
  // A stored credential only counts when we haven't switched provider —
  // a stored Anthropic key can't be reused as a GitHub/OpenAI token.
  const storedUsable = hasStoredCredential.value && provider.value === loadedProvider.value
  return storedUsable || credential.value.trim().length > 0
})

function selectProvider(value: string): void {
  if (provider.value === value) return
  provider.value = value
  credential.value = ''
  const caps = providersCaps.value.find((p) => p.provider === value)
  if (caps) authMode.value = recommendedMode(caps)
}

onMounted(async () => {
  try {
    const { data } = await api.get('/v1/settings/ai/capabilities')
    providersCaps.value = data.providers ?? []
    deploymentMode.value = data.deployment_mode ?? ''
    provider.value = data.current_provider ?? 'claude'
    loadedProvider.value = provider.value
  } catch (err: unknown) {
    const axiosErr = err as { response?: { status?: number } }
    if (axiosErr?.response?.status !== 401) {
      console.warn('[SettingsClaudeCode] failed to load capabilities', err)
    }
  }
  try {
    const { data } = await api.get('/v1/settings/claude')
    provider.value = data.provider ?? provider.value
    loadedProvider.value = provider.value
    authMode.value = data.auth_mode
    hasStoredCredential.value = data.has_api_key
  } catch (err: unknown) {
    const axiosErr = err as { response?: { status?: number } }
    if (axiosErr?.response?.status !== 401) {
      console.warn('[SettingsClaudeCode] failed to load state', err)
    }
  }
  // Reconcile: a stored mode invalid for the current provider × deployment
  // (e.g. a host-configured org now running in Full Docker, where the host
  // tile is hidden) would leave no tile selected. Fall back to the
  // recommended mode so the selection is always valid.
  const caps = currentCaps.value
  if (caps && !authOptions.value.some((o) => o.value === authMode.value)) {
    authMode.value = recommendedMode(caps)
  }
})

async function save(): Promise<void> {
  saving.value = true
  claudeError.value = ''
  try {
    const payload: {
      provider: string
      auth_mode: string
      api_key?: string
      oauth_token?: string
    } = { provider: provider.value, auth_mode: authMode.value }
    const secret = credential.value.trim()
    if (requiresSecret.value && secret.length > 0) {
      if (authMode.value === 'subscription') payload.oauth_token = secret
      else payload.api_key = secret
    }
    const { data } = await api.patch('/v1/settings/claude', payload)
    provider.value = data.provider
    loadedProvider.value = data.provider
    hasStoredCredential.value = data.has_api_key
    credential.value = ''
    await checkConnection()
  } catch (err: unknown) {
    claudeStatus.value = 'failed'
    const axiosErr = err as { response?: { data?: { detail?: string } } }
    claudeError.value = axiosErr?.response?.data?.detail
      || 'Failed to save AI settings. Try again, and check the console for details.'
    console.warn('[SettingsClaudeCode] save failed', err)
  } finally {
    saving.value = false
  }
}

async function checkConnection(): Promise<void> {
  claudeStatus.value = 'checking'
  claudeError.value = ''
  claudeVersion.value = ''
  showInstallHint.value = false
  try {
    const { data } = await api.post('/v1/settings/claude/test', null, { timeout: 120_000 })
    applyTestResult(data)
  } catch (err) {
    claudeStatus.value = 'failed'
    claudeError.value = 'Could not reach the server to test the provider CLI.'
    console.warn('[SettingsClaudeCode] test failed', err)
  }
}

function applyTestResult(data: {
  cli_available?: boolean
  test_passed?: boolean
  cli_version?: string | null
  output?: string
  error?: string | null
}): void {
  if (!data.cli_available) {
    claudeStatus.value = 'failed'
    claudeError.value = data.error || 'Provider CLI not found in the backend.'
    showInstallHint.value = true
    return
  }
  if (data.test_passed) {
    claudeStatus.value = 'passed'
    claudeVersion.value = data.cli_version || data.output || ''
  } else {
    claudeStatus.value = 'failed'
    claudeError.value = data.error || 'CLI is installed but the connection test failed.'
  }
}
</script>

<style scoped>
.auth-mode-tiles {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.auth-tile {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  background: rgba(var(--v-theme-surface-variant), 0.25);
  text-align: left;
  cursor: pointer;
  transition: border-color 120ms ease, background-color 120ms ease;
}

.auth-tile:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
  background: rgba(var(--v-theme-surface-variant), 0.4);
}

.auth-tile:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.auth-tile--active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}

.auth-tile__indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  padding-top: 1px;
  flex: 0 0 auto;
}

.auth-tile__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1 1 auto;
}

.auth-tile__header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.auth-tile__icon {
  opacity: 0.85;
}

.auth-tile__badge {
  height: 18px;
  font-size: 10px;
  letter-spacing: 0.02em;
}

.auth-tile__desc {
  line-height: 1.5;
}
</style>
