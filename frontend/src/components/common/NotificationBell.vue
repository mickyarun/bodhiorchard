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
    location="bottom end"
    :offset="6"
    :close-on-content-click="false"
    max-width="420"
  >
    <template #activator="{ props: menuProps }">
      <v-btn
        v-bind="menuProps"
        icon
        variant="text"
        size="default"
        density="comfortable"
        class="notification-bell-btn"
        :aria-label="bellLabel"
      >
        <v-badge
          :content="totalUnread"
          max="99"
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

    <NotificationTray :viewer-id="userId" @close="menuOpen = false" />
  </v-menu>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import NotificationTray from '@/components/notifications/NotificationTray.vue'
import { useNotificationSocket } from '@/composables/useNotificationSocket'
import { usePermissions } from '@/composables/usePermissions'
import { useYieldOfferSocket } from '@/composables/useYieldOfferSocket'
import { useMembersStore } from '@/stores/members'
import { useNotificationStore } from '@/stores/notifications'
import { useYieldOfferStore } from '@/stores/yieldOffers'

const props = defineProps<{ userId: string }>()

const store = useNotificationStore()
const yieldStore = useYieldOfferStore()
const membersStore = useMembersStore()
const { hasPermission, canAccessEngineering } = usePermissions()
const menuOpen = ref(false)

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
const bellLabel = computed(() =>
  totalUnread.value > 0 ? `Notifications, ${totalUnread.value} unread` : 'Notifications',
)

// Getter form (not snapshot) so the composable re-targets the WS
// subscription when ``authStore.user.id`` hydrates after this bell has
// already mounted. See ``useNotificationSocket.ts`` for the rationale.
useNotificationSocket(() => props.userId)
useYieldOfferSocket(props.userId, () => canAccessEngineering.value)

function loadMembersIfAdmin(): void {
  // Admins need the member list to translate target IDs to names on
  // offer rows and to populate the reassign selector. The members
  // endpoint is gated on team:manage so we only call it for admins.
  if (isAdmin.value && membersStore.members.length === 0) {
    void membersStore.fetchMembers()
  }
}

// Yield offers are an engineering-workspace feature: people-only roles
// would just get 403s from the offers endpoint.
function loadYieldOffers(): void {
  if (canAccessEngineering.value) void yieldStore.fetchPending(yieldScope.value)
}

onMounted(() => {
  store.fetchAll()
  loadYieldOffers()
  loadMembersIfAdmin()
})

// Re-fetch yield offers and the member list if the admin or workspace
// gate flips after mount (auth hydration race). Without this, an admin
// who was briefly unauthenticated at mount would never see org-wide
// offers and reassign targets would stay empty.
watch([yieldScope, canAccessEngineering], loadYieldOffers)
watch(isAdmin, loadMembersIfAdmin)
</script>

<style scoped>
.notification-bell-btn {
  overflow: visible !important;
}
</style>
