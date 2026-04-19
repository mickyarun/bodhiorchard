<template>
  <v-card variant="outlined" class="mcp-setup-card pa-3 text-left">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon icon="mdi-wrench" size="16" :color="iconColor" />
      <span class="text-body-2 font-weight-medium">Setup MCP Token</span>
      <v-spacer />
      <v-btn
        size="x-small"
        variant="text"
        density="comfortable"
        append-icon="mdi-open-in-new"
        :to="{ name: 'profile-mcp-token' }"
      >
        Manage
      </v-btn>
    </div>

    <div class="text-caption text-medium-emphasis mb-3">
      {{ introText }}
    </div>

    <!-- Pre-generation: compact button + one-line helper -->
    <div v-if="!newToken" class="d-flex align-center ga-2 flex-wrap">
      <v-btn
        size="x-small"
        :color="iconColor"
        variant="flat"
        :prepend-icon="generating ? undefined : 'mdi-key-plus'"
        :loading="generating"
        class="text-none generate-btn"
        @click="generate"
      >
        Generate token
      </v-btn>
      <span class="text-caption text-medium-emphasis">
        personal token — no admin needed
      </span>
    </div>

    <v-alert
      v-if="error"
      type="error"
      density="compact"
      variant="tonal"
      class="mt-2"
    >
      {{ error }}
    </v-alert>

    <!-- Post-generation: copy + run steps -->
    <v-expand-transition>
      <div v-if="newToken" class="post-gen mt-1">
        <div class="text-caption mb-1">
          Copy this export line — token is only shown once:
        </div>
        <div class="env-var-row mb-2">
          <code class="env-var-code">{{ exportLine }}</code>
          <v-tooltip :text="copied ? 'Copied!' : 'Copy export line'" location="top">
            <template #activator="{ props: tipProps }">
              <v-btn
                v-bind="tipProps"
                :icon="copied ? 'mdi-check' : 'mdi-content-copy'"
                size="x-small"
                variant="text"
                density="comfortable"
                :color="copied ? 'success' : undefined"
                aria-label="Copy export line"
                @click="copyExport"
              />
            </template>
          </v-tooltip>
        </div>
        <div class="text-caption text-medium-emphasis mb-2">
          <strong>Quit Claude Code</strong> if running, then paste the line
          into a fresh terminal in your repo and run <code>claude</code>.
          Hooks only inherit env from the shell that launches Claude Code.
        </div>
        <v-btn
          size="x-small"
          variant="text"
          density="comfortable"
          class="text-none"
          prepend-icon="mdi-refresh"
          :loading="generating"
          @click="generate"
        >
          Regenerate
        </v-btn>
      </div>
    </v-expand-transition>

    <!-- Instructions for users who already have a token configured -->
    <div v-if="!newToken && !generating" class="text-caption text-medium-emphasis mt-2">
      Already have a token?
      <a class="token-link" @click="showInstructions = !showInstructions">
        {{ showInstructions ? 'hide' : 'show' }} setup steps
      </a>
    </div>

    <v-expand-transition>
      <div v-if="showInstructions && !newToken" class="existing-token-steps mt-2">
        <ol class="setup-steps text-caption text-medium-emphasis pl-4">
          <li class="mb-1">
            <strong>Quit Claude Code</strong> if it's running in the target repo
          </li>
          <li class="mb-1">
            In a fresh terminal, <code>cd</code> to the repo and run
            <code>export BODHIORCHARD_MCP_TOKEN="your-token"</code>
          </li>
          <li class="mb-1">
            Run <code>claude</code> in the <strong>same terminal</strong> —
            the env must be set <em>before</em> <code>claude</code> starts
          </li>
          <li>
            Lost your token?
            <router-link :to="{ name: 'profile-mcp-token' }" class="token-link">
              Generate a new one
            </router-link>
          </li>
        </ol>
        <div class="stale-zshrc-warning mt-2">
          <v-icon icon="mdi-alert-outline" size="12" color="warning" class="mr-1" />
          <span class="text-caption">
            Watch out for old <code>BODHIORCHARD_MCP_TOKEN</code> exports in
            <code>~/.zshrc</code> — they override new ones on every shell.
          </span>
        </div>
      </div>
    </v-expand-transition>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

const props = withDefaults(
  defineProps<{
    purpose?: 'development' | 'testing'
  }>(),
  {
    purpose: 'development',
  },
)

// ── UI state ─────────────────────────────────────────────────────────

const generating = ref(false)
const newToken = ref<string | null>(null)
const error = ref<string | null>(null)
const copied = ref(false)
const showInstructions = ref(false)

// ── Derived ─────────────────────────────────────────────────────────

const iconColor = computed(() =>
  props.purpose === 'testing' ? 'purple' : 'primary',
)

const introText = computed(() =>
  props.purpose === 'testing'
    ? 'Connect Claude Code in your QA automation repo so test commits flow back to this BUD.'
    : 'Connect Claude Code in your development repo so commits flow back to this BUD.',
)

const exportLine = computed(() =>
  newToken.value ? `export BODHIORCHARD_MCP_TOKEN="${newToken.value}"` : '',
)

// ── Actions ─────────────────────────────────────────────────────────

async function generate(): Promise<void> {
  generating.value = true
  error.value = null
  newToken.value = null
  copied.value = false
  try {
    // Self-service endpoint — requires only authentication, no admin
    // permission. The token is returned plaintext once; the backend
    // stores a bcrypt hash. See backend/app/api/v1/me.py.
    const { data } = await api.post<{ mcp_token: string }>('/v1/me/mcp-token')
    newToken.value = data.mcp_token
  } catch (err) {
    error.value = extractApiError(err, 'Failed to generate token.')
  } finally {
    generating.value = false
  }
}


async function copyExport(): Promise<void> {
  if (!exportLine.value) return
  try {
    await navigator.clipboard.writeText(exportLine.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch (err) {
    // Non-secure context (HTTP without localhost) — fall back silently.
    // The token is still visible inline; the user can select it by hand.
    console.warn('clipboard write failed', err)
  }
}
</script>

<style scoped>
.mcp-setup-card {
  max-width: 520px;
}

/* ── Compact "Generate token" button ───────────────────────────── */

.generate-btn {
  letter-spacing: 0;
  font-size: 12px;
  font-weight: 600;
}

.post-gen {
  min-width: 0;
}

/* ── Env var code box ──────────────────────────────────────────── */

.env-var-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 4px;
}

.env-var-code {
  flex: 1;
  min-width: 0;
  font-family: ui-monospace, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.9);
  white-space: nowrap;
  overflow-x: auto;
  padding: 2px 0;
}

/* ── Existing-token fallback steps ─────────────────────────────── */

.setup-steps {
  margin: 0;
  padding-left: 18px;
}

.setup-steps li {
  line-height: 1.5;
}

.setup-steps code,
.step-body code {
  background: rgba(var(--v-theme-on-surface), 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, monospace;
  font-size: 11px;
}

.stale-zshrc-warning {
  display: flex;
  align-items: flex-start;
  padding: 6px 8px;
  background: rgba(var(--v-theme-warning), 0.08);
  border-radius: 4px;
}

.token-link {
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  text-decoration: underline;
}
</style>
