<template>
  <v-card class="pa-5 settings-card claude-card" color="surface">
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

const authOptions: ReadonlyArray<{
  value: AuthMode
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
      "Uses the host machine's claude login session or an ANTHROPIC_API_KEY env var. Nothing is stored in the database.",
  },
  {
    value: 'api_key',
    title: 'API key (Full Docker)',
    icon: 'mdi-key-variant',
    description:
      'Paste an Anthropic API key. Stored encrypted with Fernet AES-128 and applied to every agent run.',
  },
]

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
  } catch (err: unknown) {
    // 401 is expected here during first-time setup (no JWT yet). Anything
    // else — 500, network error — is worth leaving a breadcrumb for when
    // the Settings card quietly stays on defaults.
    const axiosErr = err as { response?: { status?: number } }
    if (axiosErr?.response?.status !== 401) {
      console.warn('[SettingsClaudeCode] failed to load state', err)
    }
  }
})

async function save(): Promise<void> {
  saving.value = true
  claudeError.value = ''
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
  } catch (err: unknown) {
    claudeStatus.value = 'failed'
    const axiosErr = err as { response?: { data?: { detail?: string } } }
    claudeError.value = axiosErr?.response?.data?.detail
      || 'Failed to save Claude settings. Try again, and check the console for details.'
    console.warn('[SettingsClaudeCode] save failed', err)
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
  } catch (err) {
    console.debug('[SettingsClaudeCode] authed test endpoint failed, trying setup fallback', err)
  }

  try {
    const { data } = await api.get('/setup/check-claude', { timeout: 120_000 })
    applyTestResult(data)
  } catch (err) {
    claudeStatus.value = 'failed'
    claudeError.value = 'Could not reach the server to test Claude Code.'
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
