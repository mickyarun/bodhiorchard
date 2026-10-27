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
  GitHub App setup, without a card around it. Follows the lifecycle
  status from GET /v1/settings/connections:

    - NOT_CONFIGURED   → credentials form open, "Save credentials"
    - AWAITING_INSTALL → install-on-GitHub button, plus a focus-aware poll
                         and the install socket so the page notices the
                         install as soon as the webhook lands
    - READY            → installed; credentials open on request

  Used inside the Integrations card and inside GitHubAppConnectionCard
  (setup wizard). ``flushCredentials`` / ``clearSensitiveFields`` stay
  exposed for callers that drive the save themselves.
-->
<template>
  <div class="gh-panel">
    <p v-if="status === GITHUB_APP_STATUS.READY && github.installationId" class="gh-panel__text">
      Installed on GitHub (installation #{{ github.installationId }}). Pull requests, reviews and merges flow in.
    </p>
    <GitHubAppInstallButton v-if="status === GITHUB_APP_STATUS.AWAITING_INSTALL && !formVisible" :install-url="github.installUrl" />

    <v-btn
      v-if="canToggleForm"
      variant="text"
      size="small"
      class="gh-panel__toggle"
      :prepend-icon="formVisible ? 'mdi-chevron-up' : 'mdi-pencil-outline'"
      :aria-expanded="formVisible"
      @click="userExpanded = !formVisible"
    >
      {{ formVisible ? 'Hide credentials' : 'Edit credentials' }}
    </v-btn>

    <v-expand-transition>
      <div v-if="formVisible">
        <GitHubAppCredentialsForm ref="formRef" :listen-to-store-errors="!standalone || savingHere" />
        <div v-if="standalone" class="d-flex justify-end mt-2">
          <v-btn color="primary" variant="flat" :loading="savingHere" :disabled="!dirty || savingHere" @click="onStandaloneSave">
            Save credentials
          </v-btn>
        </div>
      </div>
    </v-expand-transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GitHubAppCredentialsForm from './GitHubAppCredentialsForm.vue'
import GitHubAppInstallButton from './GitHubAppInstallButton.vue'
import { useFocusAwarePoll } from '@/composables/useFocusAwarePoll'
import { useInstallSocket } from '@/composables/useInstallSocket'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import { GITHUB_APP_STATUS, type GitHubAppStatus } from '@/types/connections'

// The install socket is the fast path; this poll is the safety net for a
// dropped socket or a subscribe-after-publish race.
const INSTALL_POLL_INTERVAL_MS = 30_000

withDefaults(
  defineProps<{
    /** Render "Save credentials" under the form for callers without their own save. */
    standalone?: boolean
  }>(),
  { standalone: false },
)

const emit = defineEmits<{ 'status-change': [GitHubAppStatus]; ready: [] }>()

const settingsStore = useSettingsStore()
const authStore = useAuthStore()
const github = computed(() => settingsStore.connections.github)
// The store normalises ``status`` on every fetch, so it is always set.
const status = computed<GitHubAppStatus>(() => github.value.status)
const isAwaitingInstall = computed(() => status.value === GITHUB_APP_STATUS.AWAITING_INSTALL)

// Not configured: the form is always open. Otherwise it opens on request.
const userExpanded = ref(false)
const canToggleForm = computed(() => status.value !== GITHUB_APP_STATUS.NOT_CONFIGURED)
const formVisible = computed(() => !canToggleForm.value || userExpanded.value)

// A lifecycle move closes the form again so it is never left open by surprise.
watch(status, (next, prev) => {
  if (next === prev) return
  userExpanded.value = false
  emit('status-change', next)
  if (next === GITHUB_APP_STATUS.READY) emit('ready')
})

useFocusAwarePoll(() => settingsStore.fetchConnections(), INSTALL_POLL_INTERVAL_MS, { active: isAwaitingInstall })

const installSocket = useInstallSocket(() => {
  void settingsStore.fetchConnections()
})
watch(
  [() => authStore.user?.org_id, isAwaitingInstall],
  ([orgId, awaiting]) => {
    if (orgId && awaiting) installSocket.start(orgId)
    else installSocket.stop()
  },
  { immediate: true },
)

const formRef = ref<InstanceType<typeof GitHubAppCredentialsForm> | null>(null)

function flushCredentials(): void {
  formRef.value?.flushCredentials()
}

function clearSensitiveFields(): void {
  formRef.value?.clearSensitiveFields()
}

// True only while this panel's own save runs, so the form shows that
// save's error and not one from another card's save.
const savingHere = ref(false)

// Unsaved credentials in the form; the Integrations page guards on it.
const dirty = defineModel<boolean>('dirty', { default: false })
watch(() => formRef.value?.dirty ?? false, d => { dirty.value = d }, { immediate: true })

async function onStandaloneSave(): Promise<void> {
  // Push the form into the store, then save only the GitHub section so the
  // form's typed error and success watchers fire as usual.
  savingHere.value = true
  const github = settingsStore.connections.github as Record<string, unknown>
  const savedAppId = github.appId
  flushCredentials()
  const ok = await settingsStore.saveConnections(['github'])
  savingHere.value = false
  if (ok) {
    clearSensitiveFields()
    return
  }
  // Take the typed values back out of the store (the form keeps them), and
  // leave the error to the form so it shows once.
  github.appId = savedAppId
  delete github.privateKey
  delete github.webhookSecret
  settingsStore.error = null
}

defineExpose({ flushCredentials, clearSensitiveFields })
</script>

<style scoped>
.gh-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gh-panel__text {
  margin: 0;
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
.gh-panel__toggle {
  align-self: flex-start;
}
</style>
