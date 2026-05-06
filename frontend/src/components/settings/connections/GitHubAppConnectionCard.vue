<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Settings → Connections → GitHub App card. Switches sub-components on
  the lifecycle status returned by GET /v1/settings/connections:

    - NOT_CONFIGURED  → credentials form expanded, "Save credentials" CTA
    - AWAITING_INSTALL → install-on-GitHub button + focus-aware poll
    - READY            → collapsed, status badge + edit toggle

  Re-exposes ``flushCredentials`` / ``clearSensitiveFields`` so the
  Settings page's existing save flow keeps working unchanged.

  Phase K — when ``standalone`` is set the card renders its own
  "Save credentials" button under the form so it can be dropped into
  contexts that don't have a parent-owned page-level Save (e.g. the
  bulk-import tab inside the setup wizard). The Settings page leaves
  ``standalone`` unset and continues to drive saves from its own button.
-->
<template>
  <v-card
    class="pa-5 settings-card"
    :class="{ 'settings-card--active': isReady }"
    color="surface"
  >
    <div class="d-flex align-center justify-space-between" :class="formVisible ? 'mb-3' : ''">
      <div class="d-flex align-center ga-3">
        <v-avatar size="36" color="surface-variant" rounded="lg">
          <v-icon icon="mdi-github" size="22" />
        </v-avatar>
        <div>
          <div class="text-body-2 font-weight-medium">GitHub App</div>
          <div class="text-caption text-medium-emphasis">PR tracking, code review &amp; webhooks</div>
        </div>
      </div>
      <div class="d-flex align-center ga-2">
        <GitHubAppStatusBadge :status="status" />
        <v-btn
          v-if="canToggleForm"
          :icon="formVisible ? 'mdi-chevron-up' : 'mdi-pencil-outline'"
          size="x-small"
          variant="text"
          :title="formVisible ? 'Collapse' : 'Edit credentials'"
          @click="userExpanded = !formVisible"
        />
      </div>
    </div>

    <v-expand-transition>
      <div v-if="formVisible">
        <GitHubAppCredentialsForm ref="formRef" />
        <div v-if="standalone" class="d-flex justify-end mt-2">
          <v-btn
            color="primary"
            variant="flat"
            :loading="settingsStore.saving"
            :disabled="settingsStore.saving"
            @click="onStandaloneSave"
          >
            {{ STANDALONE_SAVE_LABEL }}
          </v-btn>
        </div>
      </div>
    </v-expand-transition>

    <div v-if="status === GITHUB_APP_STATUS.AWAITING_INSTALL && !formVisible" class="mt-3">
      <GitHubAppInstallButton :install-url="github.installUrl" />
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import { GITHUB_APP_STATUS, type GitHubAppStatus, isGitHubAppStatus } from '@/types/connections'
import { useFocusAwarePoll } from '@/composables/useFocusAwarePoll'
import { useInstallSocket } from '@/composables/useInstallSocket'
import GitHubAppStatusBadge from './GitHubAppStatusBadge.vue'
import GitHubAppInstallButton from './GitHubAppInstallButton.vue'
import GitHubAppCredentialsForm from './GitHubAppCredentialsForm.vue'

// WS push (``org:{orgId}:install``) is the primary signal; this poll
// is a slow safety net for the subscribe-after-publish race and for
// browsers that drop the WS while the user is on the GitHub install
// page. 30 s is plenty given the WS does the fast path.
const INSTALL_POLL_INTERVAL_MS = 30_000
const STANDALONE_SAVE_LABEL = 'Save credentials'

withDefaults(
  defineProps<{
    /**
     * Render an internal "Save credentials" button under the form. Use
     * this when the card is mounted somewhere without a parent-owned
     * page-level Save (bulk-import tab, future embeds). The Settings
     * page leaves this unset and drives the save from its own button.
     */
    standalone?: boolean
  }>(),
  { standalone: false },
)

const emit = defineEmits<{
  'status-change': [GitHubAppStatus]
  ready: []
}>()

const settingsStore = useSettingsStore()
const authStore = useAuthStore()
const github = computed(() => settingsStore.connections.github)

let warnedDerived = false
const status = computed<GitHubAppStatus>(() => {
  if (isGitHubAppStatus(github.value.status)) {
    return github.value.status
  }
  // Defensive fallback — backend should always send `status` post-Phase A.
  // Warn once per page load so the regression is visible without spamming.
  if (!warnedDerived) {
    warnedDerived = true
    console.warn(
      '[GitHubAppConnectionCard] backend response missing `status`; deriving from connected/installationId.',
    )
  }
  if (!github.value.connected) {
    return GITHUB_APP_STATUS.NOT_CONFIGURED
  }
  return github.value.installationId
    ? GITHUB_APP_STATUS.READY
    : GITHUB_APP_STATUS.AWAITING_INSTALL
})

const isReady = computed(() => status.value === GITHUB_APP_STATUS.READY)
const isAwaitingInstall = computed(() => status.value === GITHUB_APP_STATUS.AWAITING_INSTALL)

// In NOT_CONFIGURED the form is always open; in the other states the user
// can opt in via the edit toggle.
const userExpanded = ref(false)
const formVisible = computed(
  () => status.value === GITHUB_APP_STATUS.NOT_CONFIGURED || userExpanded.value,
)
const canToggleForm = computed(() => status.value !== GITHUB_APP_STATUS.NOT_CONFIGURED)

// Reset the user-driven toggle whenever the lifecycle moves on, so a
// status flip doesn't strand the form expanded against the user's
// expectation.
watch(status, (next, prev) => {
  if (next !== prev) {
    userExpanded.value = false
    emit('status-change', next)
    if (next === GITHUB_APP_STATUS.READY && prev !== GITHUB_APP_STATUS.READY) {
      emit('ready')
    }
  }
})

// Focus-aware poll — only runs while AWAITING_INSTALL and the tab is
// visible. Flips off the moment status changes or focus is lost.
useFocusAwarePoll(
  () => settingsStore.fetchConnections(),
  INSTALL_POLL_INTERVAL_MS,
  { active: isAwaitingInstall },
)

// Push channel: webhook → event_bus → WS → here. On any install event
// we refetch connections so the existing ``status`` computed reacts and
// the @ready emit fires through the existing watcher above — no
// parallel state. WS subscription is scoped to AWAITING_INSTALL so we
// don't hold an idle subscription forever.
const installSocket = useInstallSocket(() => {
  void settingsStore.fetchConnections()
})

watch(
  [() => authStore.user?.org_id, isAwaitingInstall],
  ([orgId, awaiting]) => {
    if (orgId && awaiting) {
      installSocket.start(orgId)
    } else {
      installSocket.stop()
    }
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

async function onStandaloneSave(): Promise<void> {
  // Mirrors the Settings page's existing flow: push live form values
  // into the store, then call the same save action so Phase J's typed
  // error envelope and the form's success/error watchers fire normally.
  flushCredentials()
  await settingsStore.saveConnections()
}

defineExpose({ flushCredentials, clearSensitiveFields })
</script>
