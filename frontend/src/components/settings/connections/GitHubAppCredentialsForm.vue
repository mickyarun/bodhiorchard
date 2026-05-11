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

<!--
  GitHub App credential inputs (App ID, .pem, webhook secret) plus the
  inline setup-steps recipe. Owns local refs for the secret fields and
  exposes ``flushCredentials`` / ``clearSensitiveFields`` so the parent
  card forwards them up the existing Settings save flow.
-->
<template>
  <div>
    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      icon="mdi-alert-circle-outline"
      closable
      class="mb-3"
      @click:close="dismissError"
    >
      {{ errorMessage }}
    </v-alert>

    <v-alert
      v-if="showValidatedNotice"
      type="success"
      variant="tonal"
      density="compact"
      icon="mdi-check-decagram"
      class="mb-3"
    >
      Credentials validated. Now install the App on GitHub.
    </v-alert>

    <v-text-field
      v-model.number="appId"
      label="App ID"
      placeholder="123456"
      prepend-inner-icon="mdi-identifier"
      density="compact"
      variant="outlined"
      class="mb-3"
      type="number"
    />

    <v-textarea
      v-model="privateKey"
      label="Private Key (.pem)"
      :placeholder="PRIVATE_KEY_PLACEHOLDER"
      prepend-inner-icon="mdi-key-outline"
      density="compact"
      variant="outlined"
      rows="3"
      class="mb-3"
      :hint="github.hasPrivateKey ? 'Key saved. Leave empty to keep existing.' : 'Paste the .pem file contents'"
      persistent-hint
    />

    <v-text-field
      v-model="webhookSecret"
      label="Webhook Secret"
      placeholder="Set during GitHub App creation"
      prepend-inner-icon="mdi-shield-key-outline"
      density="compact"
      variant="outlined"
      class="mb-3"
      type="password"
    />

    <v-chip
      v-if="github.installationId"
      size="x-small"
      variant="tonal"
      color="success"
      prepend-icon="mdi-check-circle-outline"
      class="mb-3"
    >
      Installation #{{ github.installationId }} (auto-detected)
    </v-chip>

    <div class="text-caption text-medium-emphasis setup-steps">
      <v-icon icon="mdi-help-circle-outline" size="14" class="mr-1" />
      <strong>How to set up:</strong>
      <ol class="pl-4 mt-1 mb-0" style="line-height: 1.8;">
        <li>
          Go to your GitHub <strong>org settings</strong> &rarr; Developer settings &rarr; GitHub Apps &rarr;
          <a :href="GITHUB_NEW_APP_URL" target="_blank" rel="noopener" class="text-primary">New GitHub App</a>
        </li>
        <li>Set <strong>Webhook URL</strong> to <code>{{ webhookUrl }}</code></li>
        <li>Set <strong>Webhook Secret</strong> &mdash; generate one with <code>openssl rand -hex 32</code> and paste it in both GitHub and here</li>
        <li>Under <strong>Repository permissions</strong>: set <em>Pull requests</em> to <strong>Read &amp; Write</strong>, <em>Contents</em> to <strong>Read &amp; Write</strong>, <em>Issues</em> to <strong>Read</strong></li>
        <li>Under <strong>Subscribe to events</strong>: check <em>Pull request</em>, <em>Pull request review</em>, <em>Pull request review comment</em>, <em>Pull request review thread</em>, <em>Issue comment</em>, and <em>Issues</em></li>
        <li>Click <strong>Create GitHub App</strong> &mdash; copy the <strong>App ID</strong> and paste it above</li>
        <li>On the app page, scroll to <strong>Private keys</strong> &rarr; Generate a private key &mdash; paste the downloaded <code>.pem</code> contents above</li>
        <li>Save here, then come back to this card to finish the install handshake</li>
      </ol>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { GITHUB_APP_STATUS } from '@/types/connections'
import {
  friendlyConnectionErrorMessage,
  type ConnectionErrorPayload,
} from '@/types/connectionErrors'

const GITHUB_NEW_APP_URL = 'https://github.com/settings/apps/new'
const PRIVATE_KEY_PLACEHOLDER =
  '-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----'
const WEBHOOK_PATH = '/api/v1/webhooks/github'
const SUCCESS_NOTICE_TIMEOUT_MS = 4000

const settingsStore = useSettingsStore()
const github = computed(() => settingsStore.connections.github)

const appId = ref<number | null>(github.value.appId)
const privateKey = ref('')
const webhookSecret = ref('')
const errorMessage = ref<string>('')
const showValidatedNotice = ref(false)
let validatedTimer: ReturnType<typeof setTimeout> | null = null
// Prefer VITE_API_BASE_URL so split-host deployments (frontend on app.x, backend
// on api.x) display the correct webhook target. Falls back to the current origin
// in single-host / dev-proxy setups where the env var isn't set.
const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/api\/?$/, '')
const backendUrl = apiBase || window.location.origin
const webhookUrl = `${backendUrl}${WEBHOOK_PATH}`

watch(
  () => github.value.appId,
  (next) => { appId.value = next },
)

// Reset the inline error whenever the user edits any credential field
// — the previous attempt no longer reflects the current input.
watch([appId, privateKey, webhookSecret], () => {
  if (errorMessage.value) errorMessage.value = ''
})

// Translate the settings store's last error into a typed alert when it
// looks like a Phase J validation envelope. The store stores the
// ``detail`` body verbatim, so we parse it conservatively — anything
// that isn't a known envelope falls back to the raw string.
watch(
  () => settingsStore.error,
  (next) => {
    if (!next) return
    const parsed = parseConnectionError(next)
    errorMessage.value = parsed
      ? friendlyConnectionErrorMessage(parsed)
      : next
  },
)

// Surface a transient success notice when the org transitions to
// AWAITING_INSTALL with a freshly-fetched slug (i.e. the strict
// validator just persisted the slug). The notice auto-dismisses after
// 4 seconds so it doesn't pile up across multiple saves.
watch(
  () => [github.value.status, github.value.slug] as const,
  ([nextStatus, nextSlug], prev) => {
    const wasAwaiting = prev?.[0] === GITHUB_APP_STATUS.AWAITING_INSTALL
    const hasSlug = !!nextSlug
    const slugJustLanded = hasSlug && (!wasAwaiting || prev?.[1] !== nextSlug)
    if (nextStatus === GITHUB_APP_STATUS.AWAITING_INSTALL && slugJustLanded) {
      showValidatedNotice.value = true
      if (validatedTimer) clearTimeout(validatedTimer)
      validatedTimer = setTimeout(() => {
        showValidatedNotice.value = false
        validatedTimer = null
      }, SUCCESS_NOTICE_TIMEOUT_MS)
    }
  },
  { immediate: false },
)

function dismissError(): void {
  errorMessage.value = ''
  // Clear the store-level error too so it doesn't bleed back in on a
  // re-render of any sibling that watches the same field.
  settingsStore.error = null
}

function parseConnectionError(raw: string): ConnectionErrorPayload | null {
  // The store stringifies the FastAPI ``detail`` field. When the
  // backend returns ``{ "error": "...", "message": "..." }`` we get
  // either a JSON-shaped string or a stringified object — try both.
  if (typeof raw !== 'string') return null
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) return null
  try {
    const parsed = JSON.parse(trimmed)
    if (
      parsed
      && typeof parsed === 'object'
      && typeof parsed.error === 'string'
      && typeof parsed.message === 'string'
    ) {
      return { error: parsed.error, message: parsed.message }
    }
  } catch {
    return null
  }
  return null
}

function flushCredentials(): void {
  // Mutates the store directly — the Settings page's PATCH handler reads
  // the live store value, so writing through the same ref is the path
  // the existing save flow expects.
  const target = settingsStore.connections.github as Record<string, unknown>
  if (appId.value) {
    target.appId = appId.value
  }
  if (privateKey.value) {
    target.privateKey = privateKey.value
  }
  if (webhookSecret.value) {
    target.webhookSecret = webhookSecret.value
  }
}

function clearSensitiveFields(): void {
  privateKey.value = ''
  webhookSecret.value = ''
  appId.value = github.value.appId
}

defineExpose({ flushCredentials, clearSensitiveFields })
</script>
