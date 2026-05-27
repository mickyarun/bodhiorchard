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

<template>
  <v-menu
    v-model="menuOpen"
    location="top start"
    :close-on-content-click="false"
    max-width="420"
    min-width="360"
  >
    <template #activator="{ props: menuProps }">
      <v-btn
        v-bind="menuProps"
        icon
        variant="text"
        size="default"
        density="comfortable"
        class="notification-bell-btn"
      >
        <v-badge
          :content="totalUnread"
          :model-value="totalUnread > 0"
          color="error"
          dot-margin="-2px"
          offset-x="2"
          offset-y="2"
        >
          <v-icon icon="mdi-bell-outline" size="22" />
        </v-badge>
      </v-btn>
    </template>

    <v-card class="notification-panel" elevation="8">
      <!-- Header -->
      <v-card-title class="d-flex align-center justify-space-between pa-3 pb-1">
        <span class="text-body-1 font-weight-medium">Notifications</span>
        <v-btn
          v-if="store.unreadCount > 0"
          variant="text"
          size="small"
          density="compact"
          color="primary"
          @click="store.markAllRead()"
        >
          Mark all read
        </v-btn>
      </v-card-title>

      <v-divider />

      <!-- Yield offers section. Sits above the regular notifications
           because the actions are time-sensitive (someone else's work
           is queued behind a decision). The TARGET of an offer sees
           Accept / Reject; admins (team:manage) see Reassign for any
           offer that isn't theirs. -->
      <template v-if="yieldStore.items.length > 0">
        <div class="px-3 pt-2 pb-1 text-caption text-medium-emphasis font-weight-medium">
          Yield offers ({{ yieldStore.items.length }})
        </div>
        <v-list density="compact" class="notification-list pa-0">
          <template v-for="offer in yieldStore.items" :key="offer.id">
            <v-list-item class="notification-item notification-unread px-3 py-2">
              <template #prepend>
                <v-icon icon="mdi-flag-outline" color="warning" size="20" class="mr-3" />
              </template>
              <v-list-item-title class="text-body-2 font-weight-medium">
                BUD-{{ pad(offer.incoming_bud_number) }}
                <span class="text-warning">({{ offer.incoming_bud_priority }})</span>
                <span class="mx-1 text-medium-emphasis">↔</span>
                BUD-{{ pad(offer.yieldable_bud_number) }}
                <span class="text-medium-emphasis">({{ offer.yieldable_bud_priority }})</span>
              </v-list-item-title>
              <v-list-item-subtitle class="text-caption mt-1">
                <template v-if="isMine(offer)">
                  Your lower-priority BUD can be deprioritized.
                </template>
                <template v-else>
                  Targeted at <strong>{{ targetName(offer) }}</strong>.
                </template>
              </v-list-item-subtitle>
              <div class="d-flex ga-1 mt-2">
                <template v-if="isMine(offer)">
                  <v-btn
                    color="primary"
                    variant="flat"
                    size="x-small"
                    density="comfortable"
                    :loading="busy === offer.id"
                    @click.stop="onAccept(offer.id)"
                  >
                    Accept
                  </v-btn>
                  <v-btn
                    variant="text"
                    size="x-small"
                    density="comfortable"
                    :disabled="busy === offer.id"
                    @click.stop="askReject(offer.id)"
                  >
                    Reject
                  </v-btn>
                </template>
                <v-btn
                  v-if="isAdmin"
                  variant="text"
                  size="x-small"
                  density="comfortable"
                  :disabled="busy === offer.id"
                  @click.stop="askReassign(offer)"
                >
                  Reassign…
                </v-btn>
              </div>
            </v-list-item>
            <v-divider />
          </template>
        </v-list>
      </template>

      <!-- Notification list -->
      <v-list
        v-if="store.items.length > 0"
        density="compact"
        class="notification-list pa-0"
      >
        <template v-for="notif in store.items" :key="notif.id">
          <v-list-item
            class="notification-item px-3 py-2"
            :class="{ 'notification-unread': !notif.isRead }"
            @click="handleClick(notif)"
          >
            <template #prepend>
              <v-icon
                :icon="notifIcon(notif.type)"
                :color="notifColor(notif.type)"
                size="20"
                class="mr-3"
              />
            </template>

            <v-list-item-title class="text-body-2 font-weight-medium">
              {{ notif.title }}
            </v-list-item-title>
            <v-list-item-subtitle v-if="notif.message" class="text-caption mt-1">
              {{ notif.message }}
            </v-list-item-subtitle>
            <v-list-item-subtitle class="text-caption text-medium-emphasis mt-1">
              {{ relativeTime(notif.createdAt) }}
            </v-list-item-subtitle>

            <template #append>
              <div class="d-flex align-center ga-1">
                <v-btn
                  v-if="notif.deepLink"
                  icon
                  variant="text"
                  size="x-small"
                  density="compact"
                  @click.stop="navigateTo(notif)"
                >
                  <v-icon icon="mdi-arrow-right" size="16" />
                </v-btn>
                <v-btn
                  icon
                  variant="text"
                  size="x-small"
                  density="compact"
                  @click.stop="store.dismiss(notif.id)"
                >
                  <v-icon icon="mdi-close" size="14" />
                </v-btn>
              </div>
            </template>
          </v-list-item>
          <v-divider />
        </template>
      </v-list>

      <!-- Empty state -->
      <div v-else class="text-center pa-6 text-medium-emphasis">
        <v-icon icon="mdi-bell-check-outline" size="32" class="mb-2 d-block mx-auto" />
        <div class="text-body-2">No notifications</div>
      </div>

      <!-- Footer -->
      <template v-if="store.items.length > 0">
        <v-divider />
        <v-card-actions class="justify-center pa-2">
          <v-btn
            variant="text"
            size="small"
            density="compact"
            color="error"
            @click="handleClearAll"
          >
            Clear all
          </v-btn>
        </v-card-actions>
      </template>
    </v-card>
  </v-menu>

  <!-- Yield-offer reject confirmation. Reject is no-undo; the modal
       guards against misclicks. Accept fires immediately because it's
       a reversible action (a developer can re-request assignment). -->
  <v-dialog v-model="rejectDialog" max-width="400">
    <v-card color="surface" class="pa-5">
      <div class="text-h6 font-weight-bold mb-2">Reject this yield offer?</div>
      <div class="text-body-2 text-medium-emphasis mb-4">
        The BUD will go to the next candidate. You can't undo this.
      </div>
      <v-card-actions class="pa-0">
        <v-spacer />
        <v-btn variant="text" @click="rejectDialog = false">Cancel</v-btn>
        <v-btn color="error" variant="flat" :loading="!!busy" @click="confirmReject">
          Reject
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Admin reassign: route a pending offer to a different developer.
       Backend validates the new target holds a strictly lower-priority
       BUD and swaps yieldable_bud_id in lockstep. -->
  <v-dialog v-model="reassignDialog" max-width="440">
    <v-card color="surface" class="pa-5">
      <div class="text-h6 font-weight-bold mb-2">Reassign yield offer</div>
      <div class="text-body-2 text-medium-emphasis mb-3">
        Pick a different developer. They must already hold a BUD with priority
        strictly lower than the incoming one — the backend will pick their
        lowest-priority active BUD as the yieldable target.
      </div>
      <v-select
        v-model="reassignTargetId"
        :items="reassignTargets"
        item-title="name"
        item-value="id"
        label="New target developer"
        variant="outlined"
        density="comfortable"
        hide-details
        class="mb-3"
      />
      <v-card-actions class="pa-0">
        <v-spacer />
        <v-btn variant="text" @click="reassignDialog = false">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="!!busy"
          :disabled="!reassignTargetId"
          @click="confirmReassign"
        >
          Reassign
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '@/stores/notifications'
import { useNotificationSocket } from '@/composables/useNotificationSocket'
import { useYieldOfferStore } from '@/stores/yieldOffers'
import { useYieldOfferSocket } from '@/composables/useYieldOfferSocket'
import { useMembersStore } from '@/stores/members'
import { usePermissions } from '@/composables/usePermissions'
import type { AppNotification, YieldOffer } from '@/types'

const props = defineProps<{ userId: string }>()

// Parent (AppLayout) listens to this to freeze the sidebar's
// expand-on-hover collapse while the dropdown is open — otherwise
// moving the mouse to click a dropdown item collapses the drawer
// and unmounts this button before the click lands.
const emit = defineEmits<(e: 'update:menu-open', value: boolean) => void>()

const store = useNotificationStore()
const yieldStore = useYieldOfferStore()
const membersStore = useMembersStore()
const { hasPermission } = usePermissions()
const router = useRouter()
const menuOpen = ref(false)
watch(menuOpen, value => emit('update:menu-open', value))

const isAdmin = computed(() => hasPermission('team:manage'))
// Reactive scope: read .value at fetch time, NOT at setup. Otherwise
// if the auth store's permissions arrive after the bell mounts (slow
// hydration / stale store) we'd cache "me" and never see org-wide
// offers even when the admin gate later returns true.
const yieldScope = computed<'me' | 'org'>(() => (isAdmin.value ? 'org' : 'me'))

// Single badge count: unread notifications + pending yield offers. The
// bell is the one inbox the user checks — surfacing yield offers as
// "just another notification type" keeps the chrome compact and the
// muscle memory consistent.
const totalUnread = computed(() => store.unreadCount + yieldStore.items.length)

const busy = ref<string | null>(null)
const rejectDialog = ref(false)
const pendingReject = ref<string | null>(null)
const reassignDialog = ref(false)
const reassignTargetId = ref<string | null>(null)
const pendingReassign = ref<YieldOffer | null>(null)

const reassignTargets = computed(() => {
  const exclude = pendingReassign.value?.target_user_id ?? ''
  return membersStore.members
    .filter(m => m.isActive && m.role === 'developer' && m.id !== exclude)
    .map(m => ({ id: m.id, name: m.name }))
})

useNotificationSocket(props.userId)
useYieldOfferSocket(props.userId)

function loadMembersIfAdmin(): void {
  // Admins need the member list to translate target IDs to names on
  // offer rows and to populate the reassign selector. The members
  // endpoint is gated on team:manage so we only call it for admins.
  if (isAdmin.value && membersStore.members.length === 0) {
    void membersStore.fetchMembers()
  }
}

onMounted(() => {
  store.fetchAll()
  yieldStore.fetchPending(yieldScope.value)
  loadMembersIfAdmin()
})

// Re-fetch yield offers and the member list if the admin gate flips
// after mount (auth hydration race). Without this, an admin who was
// briefly unauthenticated at mount would never see org-wide offers
// and reassign targets would stay empty.
watch(yieldScope, scope => {
  void yieldStore.fetchPending(scope)
})
watch(isAdmin, loadMembersIfAdmin)

function isMine(offer: YieldOffer): boolean {
  return offer.target_user_id === props.userId
}

function targetName(offer: YieldOffer): string {
  const m = membersStore.members.find(x => x.id === offer.target_user_id)
  return m?.name ?? '(unknown)'
}

function pad(num: number | null): string {
  return String(num ?? 0).padStart(3, '0')
}

async function onAccept(id: string): Promise<void> {
  busy.value = id
  await yieldStore.accept(id)
  busy.value = null
}

function askReject(id: string): void {
  pendingReject.value = id
  rejectDialog.value = true
}

async function confirmReject(): Promise<void> {
  if (!pendingReject.value) return
  busy.value = pendingReject.value
  await yieldStore.reject(pendingReject.value)
  busy.value = null
  rejectDialog.value = false
  pendingReject.value = null
}

function askReassign(offer: YieldOffer): void {
  pendingReassign.value = offer
  reassignTargetId.value = null
  reassignDialog.value = true
}

async function confirmReassign(): Promise<void> {
  if (!pendingReassign.value || !reassignTargetId.value) return
  busy.value = pendingReassign.value.id
  const ok = await yieldStore.reassign(pendingReassign.value.id, reassignTargetId.value)
  busy.value = null
  if (ok) {
    reassignDialog.value = false
    pendingReassign.value = null
    reassignTargetId.value = null
  }
}

function handleClick(notif: AppNotification): void {
  if (!notif.isRead) {
    store.markRead(notif.id)
  }
  if (notif.deepLink) {
    navigateTo(notif)
  }
}

function navigateTo(notif: AppNotification): void {
  if (!notif.isRead) {
    store.markRead(notif.id)
  }
  menuOpen.value = false
  if (notif.deepLink) {
    router.push(notif.deepLink)
  }
}

function handleClearAll(): void {
  store.dismissAll()
  menuOpen.value = false
}

function notifIcon(type: string): string {
  switch (type) {
    case 'job_failed': return 'mdi-alert-circle'
    case 'approval_requested': return 'mdi-bell-ring-outline'
    case 'approval_granted': return 'mdi-check-decagram'
    case 'approval_rejected': return 'mdi-close-circle-outline'
    case 'developer_assigned': return 'mdi-account-check'
    case 'reassignment_done': return 'mdi-swap-horizontal'
    default: return 'mdi-check-circle'
  }
}

function notifColor(type: string): string {
  switch (type) {
    case 'job_failed':
    case 'approval_rejected': return 'error'
    case 'approval_requested': return 'warning'
    case 'developer_assigned':
    case 'reassignment_done': return 'info'
    default: return 'success'
  }
}

function relativeTime(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  if (diffSec < 60) return 'just now'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay}d ago`
}
</script>

<style scoped>
.notification-bell-btn {
  overflow: visible !important;
}

.notification-panel {
  max-height: 480px;
  display: flex;
  flex-direction: column;
}

.notification-list {
  overflow-y: auto;
  max-height: 360px;
}

.notification-unread {
  background: rgba(var(--v-theme-primary), 0.04);
}

.notification-item:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
  cursor: pointer;
}
</style>
