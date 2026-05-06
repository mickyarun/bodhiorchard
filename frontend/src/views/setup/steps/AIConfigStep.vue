<template>
  <div class="d-flex flex-column align-center">
    <v-icon icon="mdi-robot-outline" size="48" color="primary" class="mb-4" />
    <h2 class="text-h5 font-weight-bold mb-2">AI Engine</h2>
    <p class="text-body-2 text-medium-emphasis mb-6 text-center" style="max-width: 520px;">
      Bodhiorchard uses Claude to analyze your codebase.
      We detected how the backend is running and prefilled the right option.
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
        <!-- Host mode: let the user choose between Hybrid and Cloud API.
             Docker mode is locked to api_key — a container can't reach a
             host claude login session, so the chooser would be a footgun. -->
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

        <!-- Context alert for the active (deployment, authMode) combination -->
        <v-alert
          v-if="deploymentMode === 'docker'"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          icon="mdi-information-outline"
        >
          <div class="text-body-2">
            Backend runs inside a container, so it can't reach a host
            <code>claude login</code>. Paste an Anthropic API key and we'll
            store it encrypted on your org.
          </div>
        </v-alert>
        <v-alert
          v-else-if="authMode === 'host'"
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
          v-else
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          icon="mdi-cloud-outline"
        >
          <div class="text-body-2">
            Skip the host CLI session and call the Anthropic API directly.
            The key is encrypted on your org and applied to every agent run.
          </div>
        </v-alert>

        <!-- API key entry — shown whenever the active mode is api_key -->
        <template v-if="authMode === 'api_key'">
          <v-text-field
            v-model="apiKey"
            label="Anthropic API key"
            placeholder="sk-ant-…"
            type="password"
            variant="outlined"
            density="comfortable"
            autocomplete="off"
            hide-details
            prepend-inner-icon="mdi-key-variant"
            class="mb-2"
            :readonly="setupStore.orgInitDone"
          />
          <div class="text-caption text-medium-emphasis mb-4 ml-1">
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
              Connected to Claude <strong>{{ claudeVersion }}</strong>.
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
            <div
              v-if="deploymentMode === 'host' && authMode === 'host' && showHostInstallHint"
              class="text-caption mt-2"
            >
              Install the CLI on your host:
              <code class="text-primary">curl -fsSL https://claude.ai/install.sh | bash</code>
            </div>
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
        <v-chip variant="outlined" size="small" prepend-icon="mdi-code-braces">
          Codex
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
import type { ClaudeAuthMode } from '@/types/setup'

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
watch([apiKey, authMode], () => {
  if (testStatus.value !== 'idle' && testStatus.value !== 'checking') {
    testStatus.value = 'idle'
    testError.value = ''
  }
  setupStore.state.claude.testPassed = false
  setupStore.state.claude.testedVersion = ''
})

const showAuthChooser = computed(() => deploymentMode.value === 'host')

const authOptions: ReadonlyArray<{
  value: ClaudeAuthMode
  title: string
  icon: string
  description: string
  badge?: string
}> = [
  {
    value: 'host',
    title: 'Hybrid / host login',
    icon: 'mdi-laptop',
    badge: 'Recommended',
    description:
      "Uses the host machine's claude login session. Best for Claude Pro/Max subscribers — nothing is stored.",
  },
  {
    value: 'api_key',
    title: 'Cloud API key',
    icon: 'mdi-cloud-outline',
    description:
      'Paste an Anthropic API key. Stored encrypted with Fernet AES-128 and applied to every agent run.',
  },
]

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
  return authMode.value === 'api_key' && apiKey.value.trim().length === 0
})

const buttonLabel = computed<string>(() => {
  if (testStatus.value === 'passed') return 'Connected'
  if (testStatus.value === 'failed') return 'Retry connection test'
  return authMode.value === 'api_key'
    ? 'Test key & connect'
    : 'Test host connection'
})

// In host-login mode, surface the "install CLI on host" hint only when the
// CLI itself is missing — not when the CLI exists but auth fails.
const showHostInstallHint = computed(() => cliUnavailable.value)

const failureMessage = computed<string>(() => {
  if (cliUnavailable.value) {
    return deploymentMode.value === 'docker'
      ? 'The Claude CLI is missing from the backend container. Rebuild the backend image (docker compose build backend) and try again.'
      : 'Claude Code CLI not found on the host. Install it and retry.'
  }
  if (authMode.value === 'api_key') {
    if (testError.value.toLowerCase().includes('not logged in')) {
      return 'The backend doesn\'t see the API key yet. Paste one above and retry.'
    }
    return testError.value || 'The key was rejected. Double-check it and retry.'
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
    const { data } = await api.get('/setup/deployment-info')
    deploymentMode.value = data.mode === 'docker' ? 'docker' : 'host'
    // Apply the backend's recommended auth mode only on the first visit.
    // On later remounts, respect whatever the user explicitly chose.
    if (!setupStore.state.claude.initialized) {
      const recommended: ClaudeAuthMode = data.claude_auth_recommended === 'api_key'
        ? 'api_key'
        : 'host'
      setupStore.state.claude.authMode = recommended
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
      '/setup/check-claude',
      {
        authMode: authMode.value,
        apiKey: authMode.value === 'api_key' ? apiKey.value : null,
      },
      { timeout: 120_000 },
    )

    if (!data.cli_available) {
      testStatus.value = 'failed'
      cliUnavailable.value = true
      testError.value = data.error || 'Claude CLI not available.'
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
