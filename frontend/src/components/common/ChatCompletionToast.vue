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
  Global "BUD job finished elsewhere" snackbar.

  Surfaces job_completed / job_failed notifications as a transient
  v-snackbar with a Review CTA. Dismiss (auto-timeout, X click, or
  Review click) routes through ``store.markRead`` so the same item
  cannot re-surface on subsequent renders — the filter excludes any
  ``isRead`` notification, and Pinia's reactive items array keeps the
  computed in sync without any local-ref shenanigans.

  Sibling-pattern to XPToast.vue — single mount in AppLayout, reads
  the existing useNotificationStore, no extra socket subscriptions.

  Explicitly does NOT auto-navigate. The only ``router.push`` here is
  inside ``review()``, gated on a real ``@click`` from the Review
  button. The bell still owns the cumulative history list.
-->

<template>
  <div class="chat-completion-toast-container">
    <transition-group name="toast-slide">
      <v-snackbar
        v-for="toast in toasts"
        :key="toast.id"
        :model-value="true"
        :timeout="TOAST_TIMEOUT_MS"
        location="bottom right"
        color="surface"
        variant="flat"
        rounded="lg"
        class="chat-completion-toast"
        @update:model-value="onAutoClose(toast)"
      >
        <div class="d-flex align-center ga-3">
          <v-icon
            :icon="toast.type === 'job_failed' ? 'mdi-alert-circle' : 'mdi-check-circle'"
            :color="toast.type === 'job_failed' ? 'error' : 'primary'"
            size="22"
          />
          <div class="flex-grow-1">
            <div class="text-body-2 font-weight-medium">
              {{ toast.title }}
            </div>
            <div
              v-if="toast.message"
              class="text-caption text-medium-emphasis"
            >
              {{ toast.message }}
            </div>
          </div>
        </div>

        <template #actions>
          <v-btn
            v-if="toast.deepLink"
            variant="text"
            size="small"
            color="primary"
            class="text-none"
            @click="review(toast)"
          >
            Review
          </v-btn>
          <v-btn
            variant="text"
            size="small"
            icon="mdi-close"
            @click="dismiss(toast)"
          />
        </template>
      </v-snackbar>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useNotificationStore } from '@/stores/notifications'
import type { AppNotification } from '@/types'

// Auto-dismiss after 10s. Manual dismiss + Review click both mark the
// notification read which is what makes it stop re-surfacing — no
// local Set needed.
const TOAST_TIMEOUT_MS = 10_000

// Notification types we surface as toasts. Excludes race-invite
// (handled by RaceInviteToast) and workflow-event types that are
// only meaningful in the bell history (approval, developer_assigned,
// reassignment_done).
const TOAST_TYPES = new Set<AppNotification['type']>([
  'job_completed',
  'job_failed',
])

const store = useNotificationStore()
const { items } = storeToRefs(store)
const route = useRoute()
const router = useRouter()

// Strip ``?tab=…`` from the deep link so a same-BUD link is suppressed
// regardless of which sub-tab the notification points at.
function deepLinkBudPath(deepLink: string): string {
  const qIdx = deepLink.indexOf('?')
  return qIdx === -1 ? deepLink : deepLink.slice(0, qIdx)
}

function currentBudPath(): string | null {
  // ``/buds/<uuid>`` (detail) → ``/buds/<uuid>``.
  // ``/buds`` (board)         → ``null`` (show toast — board doesn't render
  //                                       the per-BUD chat, so a notice helps).
  // ``/dashboard``            → ``null``.
  const match = route.path.match(/^\/buds\/[^/]+/)
  return match ? match[0] : null
}

const toasts = computed<AppNotification[]>(() => {
  const here = currentBudPath()
  return items.value.filter((n) => {
    // ``isRead`` is the single source-of-truth dismiss signal.
    // Marking read removes the toast across re-renders, across route
    // changes, and across tab refreshes — no local-ref state needed.
    if (n.isRead || n.isDismissed) return false
    if (!TOAST_TYPES.has(n.type)) return false
    if (!n.deepLink) return false
    // Suppress toasts pointing at the BUD the user is already on.
    if (here && deepLinkBudPath(n.deepLink) === here) return false
    return true
  })
})

// All three dismiss paths funnel through ``markRead``:
//   - Manual X click  (``dismiss``)
//   - Auto-timeout    (``onAutoClose``)
//   - Review click    (``review``)
// This is intentional — once the user has seen the toast, the bell
// should also stop badging it as unread.

function dismiss(notif: AppNotification): void {
  void store.markRead(notif.id)
}

function onAutoClose(notif: AppNotification): void {
  void store.markRead(notif.id)
}

function review(notif: AppNotification): void {
  if (!notif.deepLink) return
  void store.markRead(notif.id)
  router.push(notif.deepLink)
}
</script>

<style scoped>
.chat-completion-toast-container {
  position: fixed;
  z-index: 2010;
  pointer-events: none;
}

.chat-completion-toast {
  pointer-events: auto;
}

.toast-slide-enter-active,
.toast-slide-leave-active {
  transition: all 0.25s ease;
}

.toast-slide-enter-from {
  opacity: 0;
  transform: translateX(20px);
}

.toast-slide-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
