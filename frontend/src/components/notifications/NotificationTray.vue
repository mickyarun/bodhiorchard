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

<!-- The notification tray behind the bell: yield offers first (they are
     time-sensitive), then notifications, newest first. Clearing all asks
     first, since it can't be undone. -->
<template>
  <!-- Enter is stopped here: the menu would otherwise cancel it, so a
       focused row or button would not activate from the keyboard. -->
  <section class="tray elevation-8" aria-labelledby="tray-title" @keydown.enter.stop>
    <header class="tray__head">
      <h2 id="tray-title" class="tray__title">Notifications</h2>
      <span v-if="unread" class="tray__count">{{ unread }} unread</span>
      <v-btn v-if="store.unreadCount > 0" variant="text" size="small" class="ml-auto" @click="store.markAllRead()">
        Mark all read
      </v-btn>
    </header>

    <div v-if="total" class="tray__scroll">
      <template v-if="yieldStore.items.length">
        <h3 class="tray__group">Yield offers</h3>
        <ul class="tray__list">
          <YieldOfferRow
            v-for="offer in yieldStore.items"
            :key="offer.id"
            :offer="offer"
            :mine="offer.target_user_id === viewerId"
            :can-reassign="isAdmin"
            :target-name="targetName(offer.target_user_id)"
            :busy="busy === offer.id"
            @accept="onAccept(offer.id)"
            @reject="askReject(offer.id)"
            @reassign="askReassign(offer)"
          />
        </ul>
        <h3 v-if="store.items.length" class="tray__group">Notifications</h3>
      </template>
      <ul v-if="store.items.length" class="tray__list">
        <NotificationRow
          v-for="notif in store.items"
          :key="notif.id"
          :notif="notif"
          :viewer-id="viewerId"
          :now="now"
          :declining="store.pendingDeclineIds.has(notif.id)"
          @open="open(notif)"
          @dismiss="store.dismiss(notif.id)"
          @decline="kind => decline(notif.id, kind)"
        />
      </ul>
    </div>

    <div v-else class="tray__empty">
      <v-icon icon="mdi-bell-check-outline" size="28" aria-hidden="true" />
      <p class="tray__empty-title">You're all caught up</p>
      <p class="tray__empty-sub">New notifications show up here.</p>
    </div>

    <footer v-if="store.items.length" class="tray__foot">
      <v-btn ref="clearButton" variant="text" size="small" @click="confirmClear = true">Clear all</v-btn>
    </footer>

    <AppConfirmDialog
      v-model="confirmClear"
      title="Clear all notifications?"
      body="This removes every notification in the tray. It can't be undone."
      action="Clear all"
      @confirm="clearAll"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppConfirmDialog from '@/components/common/AppConfirmDialog.vue'
import NotificationRow from '@/components/notifications/NotificationRow.vue'
import YieldOfferRow from '@/components/notifications/YieldOfferRow.vue'
import { useNow } from '@/composables/useNow'
import { usePermissions } from '@/composables/usePermissions'
import { useYieldOfferActions } from '@/composables/useYieldOfferActions'
import { useMembersStore } from '@/stores/members'
import { useNotificationStore } from '@/stores/notifications'
import { useYieldOfferStore } from '@/stores/yieldOffers'
import type { AppNotification } from '@/types'
import type { DeclinableInvite } from '@/utils/notificationVisuals'

defineProps<{ viewerId: string }>()
const emit = defineEmits<{ close: [] }>()

const store = useNotificationStore()
const yieldStore = useYieldOfferStore()
const membersStore = useMembersStore()
const router = useRouter()
const now = useNow()
const { hasPermission } = usePermissions()
// Reject / reassign dialogs live layout-wide in YieldOfferDialogs; the
// shared composable keeps the in-flight `busy` flag in step with them.
const { busy, onAccept, askReject, askReassign } = useYieldOfferActions()

const confirmClear = ref(false)
const clearButton = ref<{ $el: HTMLElement } | null>(null)
// Back to the button when the confirmation closes without clearing.
watch(confirmClear, async (open) => {
  if (open) return
  await nextTick()
  clearButton.value?.$el.focus()
})
const isAdmin = computed(() => hasPermission('team:manage'))
const unread = computed(() => store.unreadCount + yieldStore.items.length)
const total = computed(() => store.items.length + yieldStore.items.length)

function targetName(userId: string): string {
  return membersStore.members.find(m => m.id === userId)?.name ?? 'someone else'
}

/** Mark it read, then go where it points, closing the tray. */
function open(notif: AppNotification): void {
  if (!notif.isRead) void store.markRead(notif.id)
  if (!notif.deepLink) return
  emit('close')
  void router.push(notif.deepLink)
}

function decline(id: string, kind: DeclinableInvite): void {
  void (kind === 'race' ? store.declineRaceInvite(id) : store.declineBacklashInvite(id))
}

function clearAll(): void {
  void store.dismissAll()
  confirmClear.value = false
  emit('close')
}

</script>

<style scoped src="./notification-tray.css"></style>
