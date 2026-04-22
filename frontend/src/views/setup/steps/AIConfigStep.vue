<template>
  <div class="d-flex flex-column align-center">
    <v-icon icon="mdi-robot-outline" size="48" color="primary" class="mb-4" />
    <h2 class="text-h5 font-weight-bold mb-2">AI Engine</h2>
    <p class="text-body-2 text-medium-emphasis mb-6 text-center" style="max-width: 520px;">
      Bodhiorchard uses Claude Code to analyze your codebase.
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
          v-if="deploymentLoaded"
          :color="deploymentMode === 'docker' ? 'info' : 'success'"
          variant="tonal"
          size="small"
          :prepend-icon="deploymentMode === 'docker' ? 'mdi-docker' : 'mdi-laptop'"
        >
          {{ deploymentMode === 'docker' ? 'Full Docker' : 'Hybrid' }}
        </v-chip>
      </div>

      <!-- Docker mode: API key is the only path -->
      <template v-if="deploymentMode === 'docker'">
        <v-alert
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

        <v-btn
          :color="testStatus === 'passed' ? 'success' : 'primary'"
          :loading="testStatus === 'checking'"
          :prepend-icon="testStatus === 'passed' ? 'mdi-check-circle' : 'mdi-play-circle-outline'"
          :disabled="apiKey.trim().length === 0"
          variant="flat"
          block
          size="large"
          @click="testConnection"
        >
          {{ buttonLabel }}
        </v-btn>
      </template>

      <!-- Host mode: backend runs on the host, trust the existing login -->
      <template v-else-if="deploymentMode === 'host'">
        <v-alert
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

        <v-btn
          :color="testStatus === 'passed' ? 'success' : 'primary'"
          :loading="testStatus === 'checking'"
          :prepend-icon="testStatus === 'passed' ? 'mdi-check-circle' : 'mdi-play-circle-outline'"
          variant="flat"
          block
          size="large"
          @click="testConnection"
        >
          {{ buttonLabel }}
        </v-btn>
      </template>

      <!-- Detecting deployment mode (brief) -->
      <template v-else>
        <div class="d-flex align-center justify-center py-4 ga-2">
          <v-progress-circular indeterminate size="20" width="2" />
          <span class="text-caption text-medium-emphasis">Detecting environment…</span>
        </div>
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
              Connected to Claude Code <strong>{{ claudeVersion }}</strong>.
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
              v-if="deploymentMode === 'host' && showHostInstallHint"
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
        <v-chip variant="outlined" size="small" prepend-icon="mdi-cloud-outline">
          Cloud API
          <template #append>
            <v-chip size="x-small" variant="tonal" color="primary" class="ml-2">Soon</v-chip>
          </template>
        </v-chip>
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
import { computed, onMounted, ref, watch } from 'vue'
import api from '@/services/api'
import { useSetupStore } from '@/stores/setup'
import type { ClaudeAuthMode } from '@/types/setup'

const setupStore = useSetupStore()

const deploymentMode = ref<'docker' | 'host' | null>(null)
const deploymentLoaded = computed(() => deploymentMode.value !== null)

const apiKey = computed<string>({
  get: () => setupStore.state.claude.apiKey,
  set: (v) => { setupStore.state.claude.apiKey = v },
})

const testStatus = ref<'idle' | 'checking' | 'passed' | 'failed'>('idle')
const claudeVersion = ref('')
const testError = ref('')
const cliUnavailable = ref(false)

// Re-prompt a new test whenever the key changes.
watch(apiKey, () => {
  if (testStatus.value !== 'idle' && testStatus.value !== 'checking') {
    testStatus.value = 'idle'
    testError.value = ''
  }
})

const buttonLabel = computed<string>(() => {
  if (testStatus.value === 'passed') return 'Connected'
  if (testStatus.value === 'failed') return 'Retry connection test'
  return deploymentMode.value === 'docker'
    ? 'Test key & connect'
    : 'Test host connection'
})

// In host mode, surface the "install CLI on host" hint only when the CLI
// itself is missing — not when the CLI exists but auth fails.
const showHostInstallHint = computed(() => cliUnavailable.value)

const failureMessage = computed<string>(() => {
  if (deploymentMode.value === 'docker') {
    if (cliUnavailable.value) {
      return (
        'The Claude CLI is missing from the backend container. Rebuild the '
        + 'backend image (docker compose build backend) and try again.'
      )
    }
    // Most likely cause inside Docker: the pasted key is rejected by Anthropic.
    if (testError.value.toLowerCase().includes('not logged in')) {
      return 'The backend doesn\'t have an API key yet. Paste one above and retry.'
    }
    return testError.value || 'The key was rejected. Double-check it and retry.'
  }
  // host mode
  if (cliUnavailable.value) {
    return 'Claude Code CLI not found on the host. Install it and retry.'
  }
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
    // Align the persisted auth choice with the detected environment so the
    // /setup/initialize payload carries the right value even if the user
    // never manually interacts with this step.
    const recommended: ClaudeAuthMode = data.claude_auth_recommended === 'api_key'
      ? 'api_key'
      : 'host'
    setupStore.state.claude.authMode = recommended
  } catch {
    // Can't reach the backend — treat as host so we don't force an API key
    // input the user has no way to test.
    deploymentMode.value = 'host'
    setupStore.state.claude.authMode = 'host'
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
        authMode: deploymentMode.value === 'docker' ? 'api_key' : 'host',
        apiKey: deploymentMode.value === 'docker' ? apiKey.value : null,
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
    } else {
      testStatus.value = 'failed'
      // Capture the underlying CLI error; the computed `failureMessage`
      // narrows it to something actionable for the current deployment mode.
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
</style>
