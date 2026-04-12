<template>
  <v-container class="py-6" style="max-width: 760px;">
    <!-- Header -->
    <div class="d-flex align-center ga-2 mb-5">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        size="small"
        density="comfortable"
        :to="{ name: 'profile' }"
        aria-label="Back to profile"
      />
      <v-icon icon="mdi-key-variant" size="24" />
      <div>
        <div class="text-h6 font-weight-bold">MCP Token</div>
        <div class="text-caption text-medium-emphasis">
          Authenticate Claude Code as you for commit tracking and BUD context
        </div>
      </div>
    </div>

    <!-- Status card -->
    <v-card variant="outlined" class="pa-5 mb-4">
      <div v-if="statusLoading" class="d-flex justify-center py-6">
        <v-progress-circular indeterminate size="24" width="2" />
      </div>

      <template v-else>
        <div class="d-flex align-center ga-3 mb-4">
          <v-avatar
            :color="hasToken ? 'success' : 'warning'"
            variant="tonal"
            size="40"
          >
            <v-icon :icon="hasToken ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'" />
          </v-avatar>
          <div>
            <div class="text-body-1 font-weight-medium">
              {{ hasToken ? 'Token configured' : 'No token yet' }}
            </div>
            <div class="text-caption text-medium-emphasis">
              {{
                hasToken
                  ? 'You have a personal MCP token. Generate a new one to invalidate the old one.'
                  : 'Generate your personal MCP token to connect Claude Code.'
              }}
            </div>
          </div>
        </div>

        <v-btn
          :color="hasToken ? 'secondary' : 'primary'"
          :variant="hasToken ? 'tonal' : 'flat'"
          :prepend-icon="hasToken ? 'mdi-refresh' : 'mdi-key-plus'"
          :loading="generating"
          @click="generate"
        >
          {{ hasToken ? 'Regenerate Token' : 'Generate Token' }}
        </v-btn>

        <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mt-3">
          {{ error }}
        </v-alert>

        <!-- One-time token display -->
        <v-expand-transition>
          <v-alert
            v-if="newToken"
            type="info"
            variant="tonal"
            class="mt-4"
            icon="mdi-key"
          >
            <div class="text-body-2 font-weight-medium mb-2">
              Your MCP token — copy it now, it won't be shown again
            </div>

            <!-- Raw token row -->
            <div class="token-row mb-2">
              <code class="token-code">{{ newToken }}</code>
              <v-tooltip :text="tokenCopied ? 'Copied!' : 'Copy token'" location="top">
                <template #activator="{ props: tipProps }">
                  <v-btn
                    v-bind="tipProps"
                    :icon="tokenCopied ? 'mdi-check' : 'mdi-content-copy'"
                    size="small"
                    variant="text"
                    density="comfortable"
                    :color="tokenCopied ? 'success' : undefined"
                    @click="copyToken"
                  />
                </template>
              </v-tooltip>
            </div>

            <!-- Full export line (what you actually paste in terminal) -->
            <div class="text-caption font-weight-medium mt-3 mb-1">
              Or copy the full export line:
            </div>
            <div class="token-row">
              <code class="token-code">{{ exportLine }}</code>
              <v-tooltip :text="exportCopied ? 'Copied!' : 'Copy export line'" location="top">
                <template #activator="{ props: tipProps }">
                  <v-btn
                    v-bind="tipProps"
                    :icon="exportCopied ? 'mdi-check' : 'mdi-content-copy'"
                    size="small"
                    variant="text"
                    density="comfortable"
                    :color="exportCopied ? 'success' : undefined"
                    @click="copyExport"
                  />
                </template>
              </v-tooltip>
            </div>
          </v-alert>
        </v-expand-transition>
      </template>
    </v-card>

    <!-- Setup instructions -->
    <v-card variant="outlined" class="pa-5">
      <div class="d-flex align-center ga-2 mb-3">
        <v-icon icon="mdi-wrench" size="18" color="primary" />
        <span class="text-body-1 font-weight-medium">Setup Claude Code</span>
      </div>

      <ol class="setup-steps text-body-2 pl-5">
        <li class="mb-2">
          <strong>Quit Claude Code first</strong> if it's running. The env var
          must be set <em>before</em> <code>claude</code> starts — already-running
          sessions don't pick up new shell env.
        </li>
        <li class="mb-2">
          Open a terminal, <code>cd</code> into your repo, and run the
          <strong>full export line</strong> above. Paste it verbatim — the
          quotes and full token.
        </li>
        <li class="mb-2">
          In the <strong>same terminal</strong>, launch Claude Code:
          <div class="inline-cmd mt-1"><code>claude</code></div>
          Hooks will inherit <code>BODHIGROVE_MCP_TOKEN</code> from the shell
          and start pushing activity.
        </li>
        <li>
          <strong>Verify it's set</strong> in the shell that launched Claude
          Code:
          <div class="inline-cmd mt-1"><code>echo $BODHIGROVE_MCP_TOKEN</code></div>
          If this is empty, the hooks will silently do nothing.
        </li>
      </ol>

      <v-alert
        type="warning"
        variant="tonal"
        density="compact"
        class="mt-4"
        icon="mdi-alert-outline"
      >
        <div class="text-body-2 font-weight-medium mb-1">Common gotcha</div>
        <div class="text-caption">
          If you have an <strong>old</strong> <code>BODHIGROVE_MCP_TOKEN</code>
          exported in <code>~/.zshrc</code> or <code>~/.bashrc</code>, every
          new terminal will re-export the stale value and override what you
          just set. Remove or comment out the old line, then open a fresh
          terminal.
        </div>
      </v-alert>
    </v-card>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

const statusLoading = ref(true)
const hasToken = ref(false)
const generating = ref(false)
const newToken = ref<string | null>(null)
const error = ref<string | null>(null)

const tokenCopied = ref(false)
const exportCopied = ref(false)

const exportLine = computed(() =>
  newToken.value ? `export BODHIGROVE_MCP_TOKEN="${newToken.value}"` : '',
)

async function loadStatus(): Promise<void> {
  statusLoading.value = true
  try {
    const { data } = await api.get<{ has_token: boolean }>('/v1/me/mcp-token/status')
    hasToken.value = data.has_token
  } catch (err) {
    error.value = extractApiError(err, 'Failed to load token status.')
  } finally {
    statusLoading.value = false
  }
}

async function generate(): Promise<void> {
  generating.value = true
  error.value = null
  newToken.value = null
  try {
    const { data } = await api.post<{ mcp_token: string; message: string }>(
      '/v1/me/mcp-token',
    )
    newToken.value = data.mcp_token
    hasToken.value = true
  } catch (err) {
    error.value = extractApiError(err, 'Failed to generate token.')
  } finally {
    generating.value = false
  }
}

async function copyToken(): Promise<void> {
  if (!newToken.value) return
  try {
    await navigator.clipboard.writeText(newToken.value)
    tokenCopied.value = true
    setTimeout(() => {
      tokenCopied.value = false
    }, 2000)
  } catch {
    // non-secure context fallback — user can still select the text
  }
}

async function copyExport(): Promise<void> {
  if (!exportLine.value) return
  try {
    await navigator.clipboard.writeText(exportLine.value)
    exportCopied.value = true
    setTimeout(() => {
      exportCopied.value = false
    }, 2000)
  } catch {
    // non-secure context fallback
  }
}

onMounted(loadStatus)
</script>

<style scoped>
.token-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.25);
  border-radius: 4px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}

.token-code {
  flex: 1;
  min-width: 0;
  font-family: ui-monospace, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.9);
  white-space: nowrap;
  overflow-x: auto;
  padding: 2px 0;
}

.setup-steps {
  margin: 0;
}

.setup-steps li {
  line-height: 1.5;
}

.setup-steps code,
.inline-cmd code {
  background: rgba(var(--v-theme-on-surface), 0.08);
  padding: 1px 6px;
  border-radius: 3px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

.inline-cmd code {
  display: inline-block;
  padding: 3px 10px;
}
</style>
