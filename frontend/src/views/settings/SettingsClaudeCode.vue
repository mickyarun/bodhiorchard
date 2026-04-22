<template>
  <v-card class="pa-6 settings-card" color="surface">
    <div class="d-flex align-center ga-3 mb-1">
      <v-avatar size="36" color="surface-variant" rounded="lg">
        <v-icon icon="mdi-console" size="22" />
      </v-avatar>
      <div class="flex-grow-1">
        <div class="text-body-1 font-weight-medium">Claude Code</div>
        <div class="text-caption text-medium-emphasis">
          Required for codebase-aware agents. Configure how the backend authenticates with Claude.
        </div>
      </div>
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

    <div class="text-body-2 font-weight-medium mb-2">Authentication mode</div>
    <v-radio-group v-model="authMode" density="compact" hide-details class="mb-3">
      <v-radio value="host">
        <template #label>
          <div>
            <div class="text-body-2">Hybrid / host login</div>
            <div class="text-caption text-medium-emphasis">
              Trust the host's <code>claude login</code> (Hybrid mode) or a
              compose-level <code>ANTHROPIC_API_KEY</code> passed through to
              the backend. Nothing stored in the database.
            </div>
          </div>
        </template>
      </v-radio>
      <v-radio value="api_key">
        <template #label>
          <div>
            <div class="text-body-2">API key (Full Docker)</div>
            <div class="text-caption text-medium-emphasis">
              Paste an Anthropic API key. Stored encrypted (Fernet AES-128).
              Applied to every agent run launched from this backend.
            </div>
          </div>
        </template>
      </v-radio>
    </v-radio-group>

    <v-expand-transition>
      <div v-if="authMode === 'api_key'" class="mb-3">
        <v-text-field
          v-model="apiKey"
          label="Anthropic API key"
          :placeholder="hasStoredKey ? '•••••••••••••••• (stored — leave blank to keep)' : 'sk-ant-…'"
          type="password"
          variant="outlined"
          density="compact"
          autocomplete="off"
          hide-details
          class="mb-2"
        />
        <div class="text-caption text-medium-emphasis">
          Generate one at
          <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">
            console.anthropic.com
          </a>.
        </div>
      </div>
    </v-expand-transition>

    <div class="d-flex ga-2 mt-2 flex-wrap">
      <v-btn
        color="primary"
        variant="flat"
        prepend-icon="mdi-content-save"
        :loading="saving"
        :disabled="!canSave"
        @click="save"
      >
        Save
      </v-btn>
      <v-btn
        variant="tonal"
        prepend-icon="mdi-connection"
        :loading="claudeStatus === 'checking'"
        @click="checkClaudeCode"
      >
        {{ claudeStatus === 'idle' ? 'Test connection' : 'Retest' }}
      </v-btn>
    </div>

    <v-expand-transition>
      <div v-if="claudeStatus === 'failed'" class="mt-3">
        <v-alert type="warning" variant="tonal" density="compact">
          <div class="text-body-2 mb-2">{{ claudeError }}</div>
          <div v-if="showInstallHint" class="text-caption">
            Install Claude Code:
            <code>curl -fsSL https://claude.ai/install.sh | bash</code>
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

type AuthMode = 'host' | 'api_key'
type Status = 'idle' | 'checking' | 'passed' | 'failed'

const authMode = ref<AuthMode>('host')
const apiKey = ref('')
const hasStoredKey = ref(false)
const saving = ref(false)

const claudeStatus = ref<Status>('idle')
const claudeError = ref('')
const claudeVersion = ref('')
const showInstallHint = ref(false)

const canSave = computed(() => {
  if (authMode.value === 'host') return true
  // api_key mode: require a key unless one is already stored
  return hasStoredKey.value || apiKey.value.trim().length > 0
})

onMounted(async () => {
  try {
    const { data } = await api.get('/v1/settings/claude')
    authMode.value = data.auth_mode
    hasStoredKey.value = data.has_api_key
  } catch {
    // First-time load: endpoint may 401 for unauthenticated setup flow — ignore.
  }
})

async function save(): Promise<void> {
  saving.value = true
  try {
    const payload: { auth_mode: AuthMode; api_key?: string } = {
      auth_mode: authMode.value,
    }
    if (authMode.value === 'api_key' && apiKey.value.trim().length > 0) {
      payload.api_key = apiKey.value.trim()
    }
    const { data } = await api.patch('/v1/settings/claude', payload)
    hasStoredKey.value = data.has_api_key
    apiKey.value = ''
    await checkClaudeCode()
  } finally {
    saving.value = false
  }
}

async function checkClaudeCode(): Promise<void> {
  claudeStatus.value = 'checking'
  claudeError.value = ''
  claudeVersion.value = ''
  showInstallHint.value = false

  // Try the authenticated, org-aware endpoint first. Fall back to the
  // unauthenticated setup check for first-time setup flows.
  try {
    const { data } = await api.post('/v1/settings/claude/test', null, { timeout: 120_000 })
    applyTestResult(data)
    return
  } catch {
    // fall through to unauth setup check
  }

  try {
    const { data } = await api.get('/setup/check-claude', { timeout: 120_000 })
    applyTestResult(data)
  } catch {
    claudeStatus.value = 'failed'
    claudeError.value = 'Could not reach the server to test Claude Code.'
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
    claudeError.value = data.error || 'Claude CLI not found in the backend.'
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
