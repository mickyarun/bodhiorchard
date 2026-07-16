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
  <div class="d-flex flex-column align-center">
    <v-icon icon="mdi-robot-outline" size="48" color="primary" class="mb-4" />
    <h2 class="text-h5 font-weight-bold bo-display mb-2">AI Engine</h2>
    <p class="text-body-2 text-medium-emphasis mb-6 text-center" style="max-width: 520px;">
      Bodhiorchard uses an AI coding agent to analyze your codebase.
      Pick a provider — we detected how the backend is running and prefilled the right auth option.
    </p>

    <v-card
      class="pa-6 card-border-dark mb-4 w-100"
      color="surface"
      style="max-width: 560px;"
    >
      <!-- Header: icon + title + detected-mode badge -->
      <div class="d-flex align-center ga-3 mb-5">
        <v-avatar size="40" color="primary" rounded="lg">
          <v-icon icon="mdi-console" size="22" color="white" />
        </v-avatar>
        <div class="flex-grow-1">
          <div class="text-body-1 font-weight-medium">Claude Code</div>
          <div class="text-caption text-medium-emphasis">
            Anthropic's codebase-aware CLI
          </div>
        </div>
        <v-chip
          v-if="headerBadge"
          :color="headerBadge.color"
          variant="tonal"
          size="small"
          :prepend-icon="headerBadge.icon"
        >
          {{ headerBadge.label }}
        </v-chip>
      </div>

      <!-- Detecting deployment mode (brief) -->
      <template v-if="!deploymentLoaded">
        <div class="d-flex align-center justify-center py-4 ga-2">
          <v-progress-circular indeterminate size="20" width="2" />
          <span class="text-caption text-medium-emphasis">Detecting environment…</span>
        </div>
      </template>

      <template v-else>
        <!-- Step 1: which agent CLI runs the tasks. -->
        <div class="section-label mb-2">
          <span class="section-label__num">1</span> Provider
        </div>
        <div
          v-if="providerOptions.length"
          role="radiogroup"
          aria-label="AI provider"
          class="auth-mode-tiles mb-5"
        >
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
                {{ prov.description }}
              </div>
            </div>
          </button>
        </div>

        <!-- Settings for a provider that runs on this machine rather than via
             a CLI. Collected here so the org is usable straight out of setup
             instead of needing a second trip to Settings. -->
        <template v-if="currentCaps?.requires_base_url">
          <v-text-field
            v-model="baseUrl"
            label="Server address"
            :placeholder="currentCaps.default_base_url ?? ''"
            variant="outlined"
            density="comfortable"
            autocomplete="off"
            prepend-inner-icon="mdi-server-network-outline"
            :hint="`Leave blank for ${currentCaps.default_base_url}`"
            persistent-hint
            class="mb-4"
          />
        </template>
        <template v-if="currentCaps?.dynamic_models">
          <v-select
            v-model="model"
            :items="currentCaps.models"
            item-title="label"
            item-value="id"
            label="Model"
            variant="outlined"
            density="comfortable"
            prepend-inner-icon="mdi-brain"
            no-data-text="No tool-capable models found"
            :hint="
              currentCaps.models.length
                ? 'Read from your server — only models that support tool calling are listed.'
                : 'None found. Check the address above, then run: ollama pull qwen3'
            "
            persistent-hint
            class="mb-4"
          />
        </template>
        <template v-if="currentCaps?.supports_thinking">
          <div class="text-body-2 font-weight-medium mb-2">Reasoning</div>
          <AppPillToggle
            v-model="thinkingChoice"
            :options="[
              { value: 'off', label: 'Off (faster)' },
              { value: 'on', label: 'On (slower)' },
            ]"
          />
          <div class="text-caption text-medium-emphasis mt-1 mb-4">
            Reasoning before answering roughly doubles response time. Off is recommended.
          </div>
        </template>

        <!-- Step 2: how the backend authenticates with the selected provider. -->
        <v-divider class="mb-4" />
        <div class="section-label mb-2">
          <span class="section-label__num">2</span> Authentication
        </div>
        <div
          v-if="showAuthChooser"
          role="radiogroup"
          aria-label="Authentication mode"
          class="auth-mode-tiles mb-4"
        >
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
                  size="x-small"
                  variant="tonal"
                  color="primary"
                  class="auth-tile__badge"
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

        <!-- Context alert (+ subscription usage warning) for the active mode -->
        <v-alert
          v-if="authMode === 'host'"
          type="success"
          variant="tonal"
          density="compact"
          class="mb-4"
          icon="mdi-laptop"
        >
          <div class="text-body-2">
            Backend runs directly on your machine, so agent runs use whichever
            <code>claude login</code> you're already signed in with. Nothing
            is stored in the database.
          </div>
        </v-alert>
        <v-alert
          v-else-if="authMode === 'subscription'"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          icon="mdi-account-key-outline"
        >
          <div class="text-body-2">
            Uses your Claude Pro/Max subscription via an OAuth token — no
            per-token API bill. The token is encrypted on your org.
          </div>
        </v-alert>
        <v-alert
          v-else
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          icon="mdi-cloud-outline"
        >
          <div class="text-body-2">
            The {{ credentialLabel }} is encrypted on your org and applied to
            every agent run.
          </div>
        </v-alert>

        <!-- Credential entry — shown whenever the active mode is api_key -->
        <template v-if="authMode === 'api_key'">
          <v-text-field
            v-model="apiKey"
            :label="credentialLabel"
            type="password"
            variant="outlined"
            density="comfortable"
            autocomplete="off"
            hide-details
            prepend-inner-icon="mdi-key-variant"
            class="mb-2"
            :readonly="setupStore.orgInitDone"
          />
          <div v-if="isClaude" class="text-caption text-medium-emphasis mb-4 ml-1">
            <v-icon icon="mdi-open-in-new" size="12" class="mr-1" />
            <a
              href="https://console.anthropic.com/settings/keys"
              target="_blank"
              rel="noopener"
              class="text-primary"
            >
              Get a key at console.anthropic.com
            </a>
          </div>
        </template>

        <!-- OAuth token entry — shown when the active mode is subscription -->
        <template v-if="authMode === 'subscription'">
          <v-text-field
            v-model="oauthToken"
            label="Claude Code OAuth token"
            placeholder="sk-ant-oat…"
            type="password"
            variant="outlined"
            density="comfortable"
            autocomplete="off"
            hide-details
            prepend-inner-icon="mdi-account-key-outline"
            class="mb-2"
            :readonly="setupStore.orgInitDone"
          />
          <div class="text-caption text-medium-emphasis mb-4 ml-1">
            <v-icon icon="mdi-console" size="12" class="mr-1" />
            Generate one with
            <code>npx @anthropic-ai/claude-code setup-token</code>, authorize
            in your browser, and paste the token here.
          </div>
        </template>

        <!-- How to connect — provider + auth-mode specific steps -->
        <div v-if="connectSteps.length" class="connect-steps mb-3">
          <div class="text-caption font-weight-medium mb-1">How to connect</div>
          <ol class="connect-steps__list">
            <li v-for="(step, i) in connectSteps" :key="i" class="text-caption text-medium-emphasis">
              {{ step }}
            </li>
          </ol>
        </div>

        <v-btn
          :color="testStatus === 'passed' ? 'success' : 'primary'"
          :loading="testStatus === 'checking'"
          :prepend-icon="testStatus === 'passed' ? 'mdi-check-circle' : 'mdi-play-circle-outline'"
          :disabled="testDisabled"
          variant="flat"
          block
          size="large"
          @click="testConnection"
        >
          {{ buttonLabel }}
        </v-btn>
      </template>

      <!-- Feedback -->
      <v-expand-transition>
        <div v-if="testStatus === 'passed'" class="mt-4">
          <v-alert
            type="success"
            variant="tonal"
            density="compact"
            icon="mdi-check-decagram"
          >
            <div class="text-body-2">
              Connected to <strong>{{ currentProviderTitle }}</strong>
              <span v-if="claudeVersion"> ({{ claudeVersion }})</span>.
            </div>
          </v-alert>
        </div>
      </v-expand-transition>
      <v-expand-transition>
        <div v-if="testStatus === 'failed'" class="mt-4">
          <v-alert
            type="error"
            variant="tonal"
            density="compact"
            icon="mdi-alert-circle-outline"
          >
            <div class="text-body-2">{{ failureMessage }}</div>
          </v-alert>
        </div>
      </v-expand-transition>
    </v-card>

    <!-- Coming-soon engines — kept compact at the bottom -->
    <div class="w-100" style="max-width: 560px;">
      <div class="text-caption mb-2 ml-1" style="opacity: 0.75;">
        More AI engines coming soon
      </div>
      <div class="d-flex flex-wrap ga-2 coming-soon-row">
        <v-chip variant="outlined" size="small" prepend-icon="mdi-server-outline">
          Ollama
          <template #append>
            <v-chip size="x-small" variant="tonal" color="primary" class="ml-2">Soon</v-chip>
          </template>
        </v-chip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch, ref } from 'vue'
import api from '@/services/api'
import { useSetupStore } from '@/stores/setup'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import type { ClaudeAuthMode } from '@/types/setup'
import {
  type AuthModeSpec,
  type ProviderCaps,
  providerIcon,
  providerTitle,
} from '@/constants/aiProviders'

const setupStore = useSetupStore()

const deploymentMode = ref<'docker' | 'host' | null>(null)
const deploymentLoaded = computed(() => deploymentMode.value !== null)

const authMode = computed<ClaudeAuthMode>({
  get: () => setupStore.state.claude.authMode,
  set: (v) => { setupStore.state.claude.authMode = v },
})

const apiKey = computed<string>({
  get: () => setupStore.state.claude.apiKey,
  set: (v) => { setupStore.state.claude.apiKey = v },
})

const oauthToken = computed<string>({
  get: () => setupStore.state.claude.oauthToken,
  set: (v) => { setupStore.state.claude.oauthToken = v },
})

const provider = computed<string>({
  get: () => setupStore.state.claude.provider,
  set: (v) => { setupStore.state.claude.provider = v },
})

const baseUrl = computed<string>({
  get: () => setupStore.state.claude.baseUrl,
  set: (v) => { setupStore.state.claude.baseUrl = v },
})
const model = computed<string>({
  get: () => setupStore.state.claude.model,
  set: (v) => { setupStore.state.claude.model = v },
})
// AppPillToggle carries string values, so the boolean is mapped at the edge.
const thinkingChoice = computed<'on' | 'off'>({
  get: () => (setupStore.state.claude.thinking ? 'on' : 'off'),
  set: (v) => { setupStore.state.claude.thinking = v === 'on' },
})

const providersCaps = ref<ProviderCaps[]>([])

const MODE_ICONS: Record<string, string> = {
  host: 'mdi-laptop',
  api_key: 'mdi-cloud-outline',
  subscription: 'mdi-account-key-outline',
}

const currentCaps = computed<ProviderCaps | undefined>(() =>
  providersCaps.value.find((p) => p.provider === provider.value),
)
const isClaude = computed(() => provider.value === 'claude')

const providerOptions = computed(() =>
  providersCaps.value.map((p) => ({
    value: p.provider,
    title: providerTitle(p.provider),
    icon: providerIcon(p.provider),
    description: p.cli
      ? `Runs via the ${p.cli} CLI.`
      : 'Runs against a server on your own machine. No CLI needed.',
  })),
)

const credentialLabel = computed(() => {
  const apiMode = currentCaps.value?.auth_modes.find((m) => m.value === 'api_key')
  return apiMode?.label ?? 'API key'
})

const currentProviderTitle = computed(() => providerTitle(provider.value))

// Provider + auth-mode specific "how to connect" steps shown above the test
// button. Plain strings (no markup) — kept short and copy-pasteable.
const connectSteps = computed<string[]>(() => {
  const p = provider.value
  const m = authMode.value
  if (p === 'copilot') {
    if (m === 'host') {
      return [
        'Install the Copilot CLI on the host: npm i -g @github/copilot',
        'Sign in with the GitHub CLI: gh auth login (or set GH_TOKEN). The account needs an active Copilot plan with the "Copilot in the CLI" policy enabled.',
        'Click "Test connection" below.',
      ]
    }
    return [
      'Create a GitHub token with Copilot access at github.com/settings/tokens.',
      'Paste it in the field above, then click "Test connection".',
    ]
  }
  if (p === 'codex') {
    if (m === 'host') {
      return [
        'Install the Codex CLI on the host: npm i -g @openai/codex',
        'Sign in: run "codex" once and complete the login (saved in ~/.codex).',
        'Click "Test connection" below.',
      ]
    }
    return [
      'Create an OpenAI API key at platform.openai.com/api-keys.',
      'Paste it in the field above, then click "Test connection".',
    ]
  }
  // claude
  if (m === 'host') {
    return [
      'Install Claude Code on the host: curl -fsSL https://claude.ai/install.sh | bash',
      'Sign in: run "claude login" (or set ANTHROPIC_API_KEY).',
      'Click "Test connection" below.',
    ]
  }
  if (m === 'subscription') {
    return [
      'Run "npx @anthropic-ai/claude-code setup-token" and authorize in the browser.',
      'Paste the token above, then click "Test connection".',
    ]
  }
  return [
    'Create an Anthropic API key at console.anthropic.com.',
    'Paste it above, then click "Test connection".',
  ]
})

function recommendedMode(caps: ProviderCaps): ClaudeAuthMode {
  if (deploymentMode.value === 'docker') {
    const cred = caps.auth_modes.find((m) => m.requires_secret)
    return (cred?.value ?? 'api_key') as ClaudeAuthMode
  }
  return (caps.auth_modes.find((m) => m.value === 'host')?.value ?? 'host') as ClaudeAuthMode
}

function selectProvider(value: string): void {
  if (provider.value === value) return
  provider.value = value
  setupStore.state.claude.apiKey = ''
  setupStore.state.claude.oauthToken = ''
  const caps = providersCaps.value.find((p) => p.provider === value)
  if (caps) authMode.value = recommendedMode(caps)
}

// Hydrate from the persisted store so navigating away and back to this step
// keeps the user's prior "Connected" feedback. Failures are treated as
// transient and not persisted — the user should re-test on revisit.
const testStatus = ref<'idle' | 'checking' | 'passed' | 'failed'>(
  setupStore.state.claude.testPassed ? 'passed' : 'idle',
)
const claudeVersion = ref(setupStore.state.claude.testedVersion)
const testError = ref('')
const cliUnavailable = ref(false)

// Re-prompt a new test whenever the user edits the key or flips auth mode —
// the prior pass/fail no longer reflects the current selection. Also clear
// the persisted "passed" flag so the green state can't survive stale inputs.
// Reset the prior pass/fail whenever the selection changes — including the
// PROVIDER, since two providers can share an auth mode (e.g. both default to
// host), in which case nothing else here would change and a stale "Connected"
// would linger.
watch([provider, apiKey, oauthToken, authMode], () => {
  if (testStatus.value !== 'idle' && testStatus.value !== 'checking') {
    testStatus.value = 'idle'
    testError.value = ''
  }
  setupStore.state.claude.testPassed = false
  setupStore.state.claude.testedVersion = ''
})

// Both deployment modes offer a chooser now: host mode picks between host
// login and a cloud API key; Docker mode picks between a cloud API key and a
// Claude subscription OAuth token (a container can't reach a host login).
const showAuthChooser = computed(() => deploymentLoaded.value)

interface AuthOption {
  value: ClaudeAuthMode
  title: string
  icon: string
  description: string
  badge?: string
}

function modeDescription(mode: AuthModeSpec): string {
  if (!mode.requires_secret) {
    return "Uses the host machine's CLI login / process env. Nothing is stored."
  }
  if (mode.value === 'subscription') {
    return 'Paste an OAuth token from `claude setup-token`. Uses your Claude plan.'
  }
  return `Paste a ${mode.label}. Stored encrypted and applied to every agent run.`
}

const authOptions = computed<ReadonlyArray<AuthOption>>(() => {
  const caps = currentCaps.value
  if (!caps) return []
  const recommended = recommendedMode(caps)
  return caps.auth_modes
    .filter((m) => !(deploymentMode.value === 'docker' && m.value === 'host'))
    .map((m) => ({
      value: m.value as ClaudeAuthMode,
      title: m.label,
      icon: MODE_ICONS[m.value] ?? 'mdi-key',
      description: modeDescription(m),
      badge: m.value === recommended ? 'Recommended' : undefined,
    }))
})

const headerBadge = computed<{ label: string; color: string; icon: string } | null>(() => {
  if (!deploymentLoaded.value) return null
  if (deploymentMode.value === 'docker') {
    return { label: 'Full Docker', color: 'info', icon: 'mdi-docker' }
  }
  if (authMode.value === 'api_key') {
    return { label: 'Cloud API', color: 'primary', icon: 'mdi-cloud-outline' }
  }
  return { label: 'Hybrid', color: 'success', icon: 'mdi-laptop' }
})

const testDisabled = computed<boolean>(() => {
  if (!deploymentLoaded.value) return true
  if (authMode.value === 'api_key') return apiKey.value.trim().length === 0
  if (authMode.value === 'subscription') return oauthToken.value.trim().length === 0
  return false
})

const buttonLabel = computed<string>(() => {
  if (testStatus.value === 'passed') return 'Connected'
  if (testStatus.value === 'failed') return 'Retry connection test'
  if (authMode.value === 'api_key') return 'Test key & connect'
  if (authMode.value === 'subscription') return 'Test token & connect'
  return 'Test host connection'
})

const failureMessage = computed<string>(() => {
  if (cliUnavailable.value) {
    // Backend returns the provider-specific install hint as the error.
    if (testError.value) return testError.value
    return deploymentMode.value === 'docker'
      ? `The ${currentProviderTitle.value} CLI is missing from the backend container. Rebuild the backend image (docker compose build backend) and try again.`
      : `${currentProviderTitle.value} CLI not found on the host. Install it and retry.`
  }
  if (authMode.value === 'api_key') {
    if (testError.value.toLowerCase().includes('not logged in')) {
      return 'The backend doesn\'t see the API key yet. Paste one above and retry.'
    }
    return testError.value || 'The key was rejected. Double-check it and retry.'
  }
  if (authMode.value === 'subscription') {
    return testError.value
      || 'The token was rejected. Run `claude setup-token` again and paste a fresh one.'
  }
  // host login mode
  if (testError.value.toLowerCase().includes('not logged in')) {
    return 'Run `claude login` on your host to authenticate, then retry.'
  }
  return testError.value || 'Claude Code test failed.'
})

onMounted(async () => {
  await detectDeployment()
})

async function detectDeployment(): Promise<void> {
  try {
    const { data } = await api.get('/setup/ai-capabilities')
    deploymentMode.value = data.deployment_mode === 'docker' ? 'docker' : 'host'
    providersCaps.value = data.providers ?? []
    // Apply the recommended auth mode for the selected provider only on the
    // first visit. On later remounts, respect the user's explicit choice.
    if (!setupStore.state.claude.initialized) {
      const caps = providersCaps.value.find((p) => p.provider === provider.value)
      if (caps) setupStore.state.claude.authMode = recommendedMode(caps)
      setupStore.state.claude.initialized = true
    }
  } catch {
    // Can't reach the backend — treat as host so we don't force an API key
    // input the user has no way to test.
    deploymentMode.value = 'host'
    if (!setupStore.state.claude.initialized) {
      setupStore.state.claude.authMode = 'host'
      setupStore.state.claude.initialized = true
    }
  }
}

async function testConnection(): Promise<void> {
  testStatus.value = 'checking'
  testError.value = ''
  cliUnavailable.value = false

  try {
    const { data } = await api.post(
      '/setup/check-ai',
      {
        provider: provider.value,
        authMode: authMode.value,
        apiKey: authMode.value === 'api_key' ? apiKey.value : null,
        oauthToken: authMode.value === 'subscription' ? oauthToken.value : null,
        // Test what the user has typed, not a default. Without these, a
        // provider running on their own machine gets probed at the default
        // address with no model, and a healthy server reports as broken.
        baseUrl: baseUrl.value || null,
        model: model.value || null,
        thinking: setupStore.state.claude.thinking,
      },
      // Generous: this is the cold request, and local inference on CPU can
      // spend most of it just loading the model into memory.
      { timeout: 400_000 },
    )

    if (!data.cli_available) {
      testStatus.value = 'failed'
      cliUnavailable.value = true
      testError.value = data.error || `${currentProviderTitle.value} CLI not available.`
      return
    }
    if (data.test_passed) {
      testStatus.value = 'passed'
      claudeVersion.value = data.cli_version || data.version || ''
      setupStore.state.claude.testPassed = true
      setupStore.state.claude.testedVersion = claudeVersion.value
    } else {
      testStatus.value = 'failed'
      // Capture the underlying CLI error; the computed `failureMessage`
      // narrows it to something actionable for the current selection.
      testError.value = data.error || data.output || 'Connection test failed.'
    }
  } catch (err: unknown) {
    testStatus.value = 'failed'
    if (err && typeof err === 'object' && 'response' in err) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      testError.value = axiosErr.response?.data?.detail || 'Server unreachable.'
    } else {
      testError.value = 'Server unreachable.'
    }
  }
}
</script>

<style scoped>
.coming-soon-row :deep(.v-chip) {
  pointer-events: none;
  cursor: default;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  opacity: 0.85;
}

.section-label__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(var(--v-theme-primary), 0.15);
  color: rgb(var(--v-theme-primary));
  font-size: 0.6875rem;
  font-weight: 700;
}

.auth-mode-tiles {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.connect-steps {
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(var(--v-theme-surface-variant), 0.25);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.connect-steps__list {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.connect-steps__list li {
  line-height: 1.5;
}

.auth-tile {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
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
