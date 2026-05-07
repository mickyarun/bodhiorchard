<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Auth sub-panel embedded in RepoCloneForm.

  Shows only the section(s) the queue actually needs:
    - HTTPS in queue → PAT input + "Create token" link with steps
    - SSH in queue   → deploy key + GitHub deploy-keys link
    - Mixed          → both, headed by clear labels
    - Empty queue    → both, dimmed, with a "queue a URL first" hint

  We always include the `Create token` micro-instructions inline so the
  user doesn't have to leave the dialog to figure out the GitHub flow.
-->
<template>
  <div class="auth-panel pa-3 rounded">
    <div v-if="!hasHttps && !hasSsh" class="text-caption text-medium-emphasis">
      Queue at least one URL — the auth method depends on whether you use
      HTTPS or SSH.
    </div>

    <!-- HTTPS / personal access token -->
    <section v-if="showHttps" :class="{ 'mb-3': showSsh }">
      <header class="d-flex align-center ga-2 mb-2">
        <v-icon icon="mdi-lock-outline" size="14" />
        <span class="text-caption font-weight-medium">HTTPS · Personal access token</span>
      </header>

      <v-text-field
        v-model="patModel"
        :placeholder="patPlaceholder"
        type="password"
        variant="outlined"
        density="compact"
        hide-details
        autocomplete="off"
        prepend-inner-icon="mdi-key"
      />

      <details class="mt-2">
        <summary class="text-caption text-medium-emphasis pat-help-summary">
          How to create a token
        </summary>
        <ol class="text-caption text-medium-emphasis pat-help-list">
          <li>
            Open
            <a
              href="https://github.com/settings/tokens?type=beta"
              target="_blank"
              rel="noopener"
              class="text-primary"
            >GitHub → fine-grained tokens</a> and click <em>Generate new token</em>.
          </li>
          <li>Limit access to the repos you want Bodhiorchard to clone.</li>
          <li>Under <em>Repository permissions</em>, set <strong>Contents: Read</strong>.</li>
          <li>Generate, copy the token (starts with <code>github_pat_…</code>) and paste it above.</li>
        </ol>
      </details>
    </section>

    <!-- SSH / deploy key -->
    <section v-if="showSsh">
      <header class="d-flex align-center justify-space-between mb-2">
        <div class="d-flex align-center ga-2">
          <v-icon icon="mdi-shield-key-outline" size="14" />
          <span class="text-caption font-weight-medium">SSH · Deploy key</span>
        </div>
        <v-btn
          v-if="deployPublicKey"
          size="x-small"
          variant="tonal"
          density="compact"
          :prepend-icon="copied ? 'mdi-check' : 'mdi-content-copy'"
          :color="copied ? 'success' : undefined"
          class="text-none"
          @click="copyKey"
        >
          {{ copied ? 'Copied' : 'Copy key' }}
        </v-btn>
      </header>

      <div v-if="deployPublicKey" class="ssh-key-box">{{ deployPublicKey }}</div>
      <div v-else class="d-flex align-center ga-2 ssh-key-box ssh-key-loading">
        <v-progress-circular indeterminate size="14" width="2" />
        <span>Generating deploy key…</span>
      </div>

      <div class="text-caption text-medium-emphasis mt-2">
        Add this to
        <a
          href="https://github.com/settings/keys"
          target="_blank"
          rel="noopener"
          class="text-primary"
        >GitHub → SSH and GPG keys</a>
        before queuing SSH URLs.
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDeploymentMode } from '@/composables/useDeploymentMode'

const props = defineProps<{
  pat: string
  hasHttps: boolean
  hasSsh: boolean
}>()

const emit = defineEmits<{
  'update:pat': [value: string]
}>()

const { deployPublicKey } = useDeploymentMode()

const patModel = computed({
  get: () => props.pat,
  set: (v: string) => emit('update:pat', v),
})

// When the queue is empty we still surface both sections (dimmed via the
// caption hint at the top) so the user can pre-stage credentials before
// adding URLs. When it has anything, we narrow to what's needed.
const queueEmpty = computed(() => !props.hasHttps && !props.hasSsh)
const showHttps = computed(() => props.hasHttps || queueEmpty.value)
const showSsh = computed(() => props.hasSsh || queueEmpty.value)

const patPlaceholder = computed(() =>
  props.hasHttps ? 'github_pat_…' : 'Token (only needed if you queue HTTPS URLs)',
)

const copied = ref(false)
let copyTimer: number | null = null

async function copyKey(): Promise<void> {
  if (!deployPublicKey.value) return
  try {
    await navigator.clipboard.writeText(deployPublicKey.value)
    copied.value = true
    if (copyTimer !== null) window.clearTimeout(copyTimer)
    copyTimer = window.setTimeout(() => { copied.value = false }, 1500)
  } catch {
    // Clipboard API can be blocked in insecure contexts; the key text
    // remains selectable so the user can copy manually.
  }
}
</script>

<style scoped>
.auth-panel {
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.pat-help-summary {
  cursor: pointer;
  user-select: none;
}

.pat-help-summary:hover {
  color: rgb(var(--v-theme-on-surface));
}

.pat-help-list {
  margin: 6px 0 0 18px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ssh-key-box {
  font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.4;
  word-break: break-all;
  padding: 8px 10px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 4px;
  user-select: all;
}

.ssh-key-loading {
  font-family: inherit;
  color: rgba(var(--v-theme-on-surface), 0.6);
  user-select: none;
}
</style>
