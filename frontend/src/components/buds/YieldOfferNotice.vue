<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 -->

<!-- Yield-offer board notice.

     Shows ALL of the current user's pending offers as a stack of
     AppCallout banners above the kanban columns. Each banner offers
     Accept (immediate; releases the lower-priority BUD and takes the
     incoming one) and Reject (confirmation modal before firing; the
     system tries the next candidate).

     Empty list → component renders nothing. Driven entirely off the
     ``useYieldOfferStore`` so updates land live via WS without any
     prop plumbing from the parent. -->
<template>
  <div v-if="store.items.length > 0" class="yield-offer-notice mb-4">
    <AppCallout
      v-for="offer in store.items"
      :key="offer.id"
      variant="warning"
      eyebrow="Yield offer"
      icon="mdi-flag-outline"
    >
      <span>
        <template v-if="isAdmin && !isMine(offer)">
          <strong>{{ targetName(offer) }}</strong> can yield BUD-{{ pad(offer.yieldable_bud_number) }}
          ({{ offer.yieldable_bud_priority }})
          to take BUD-{{ pad(offer.incoming_bud_number) }}
          <strong>({{ offer.incoming_bud_priority }})</strong>.
        </template>
        <template v-else>
          BUD-{{ pad(offer.incoming_bud_number) }}
          <strong>({{ offer.incoming_bud_priority }})</strong>
          needs you — your current
          BUD-{{ pad(offer.yieldable_bud_number) }}
          ({{ offer.yieldable_bud_priority }}) can be deprioritized.
        </template>
      </span>
      <template #actions>
        <!-- The offer's TARGET sees Accept / Reject. Admins viewing
             someone else's offer see only Reassign — accept/reject
             is the developer's decision, not the admin's. -->
        <template v-if="isMine(offer)">
          <v-btn
            color="primary"
            variant="flat"
            size="small"
            :loading="busy === offer.id"
            @click="onAccept(offer.id)"
          >
            Accept
          </v-btn>
          <v-btn
            variant="text"
            size="small"
            :disabled="busy === offer.id"
            @click="askReject(offer.id)"
          >
            Reject
          </v-btn>
        </template>
        <v-btn
          v-if="isAdmin"
          variant="text"
          size="small"
          :disabled="busy === offer.id"
          @click="askReassign(offer)"
        >
          Reassign…
        </v-btn>
      </template>
    </AppCallout>

    <!-- Reject confirmation. Reject is a no-undo step (the offer moves
         to the next candidate); a quick confirm guards against
         misclicks. Accept fires immediately because the action is
         reversible by the developer (they can request reassignment
         later). -->
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

    <!-- Admin reassign: pick a different developer to route this offer
         to. The backend validates the new target holds a strictly
         lower-priority BUD and swaps yieldable_bud_id accordingly. -->
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useYieldOfferStore } from '@/stores/yieldOffers'
import { useAuthStore } from '@/stores/auth'
import { useMembersStore } from '@/stores/members'
import { usePermissions } from '@/composables/usePermissions'
import type { YieldOffer } from '@/types'

const store = useYieldOfferStore()
const authStore = useAuthStore()
const membersStore = useMembersStore()
const { hasPermission } = usePermissions()

const isAdmin = computed(() => hasPermission('team:manage'))
const currentUserId = computed(() => authStore.user?.id ?? '')

const busy = ref<string | null>(null)
const rejectDialog = ref(false)
const pendingReject = ref<string | null>(null)
const reassignDialog = ref(false)
const reassignTargetId = ref<string | null>(null)
const pendingReassign = ref<YieldOffer | null>(null)

// Eligible reassignment targets: every active developer in the org
// EXCEPT the offer's current target (no-op self-reassign). The backend
// further validates they hold a lower-priority BUD.
const reassignTargets = computed(() => {
  const exclude = pendingReassign.value?.target_user_id ?? ''
  return membersStore.members
    .filter(m => m.isActive && m.role === 'developer' && m.id !== exclude)
    .map(m => ({ id: m.id, name: m.name }))
})

function isMine(offer: YieldOffer): boolean {
  return offer.target_user_id === currentUserId.value
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
  await store.accept(id)
  busy.value = null
}

function askReject(id: string): void {
  pendingReject.value = id
  rejectDialog.value = true
}

async function confirmReject(): Promise<void> {
  if (!pendingReject.value) return
  busy.value = pendingReject.value
  await store.reject(pendingReject.value)
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
  const ok = await store.reassign(pendingReassign.value.id, reassignTargetId.value)
  busy.value = null
  if (ok) {
    reassignDialog.value = false
    pendingReassign.value = null
    reassignTargetId.value = null
  }
}

function loadMembersIfAdmin(): void {
  if (isAdmin.value && membersStore.members.length === 0) {
    void membersStore.fetchMembers()
  }
}

onMounted(loadMembersIfAdmin)
// Re-fetch if the admin gate flips after mount (auth hydration race).
watch(isAdmin, loadMembersIfAdmin)
</script>

<style scoped>
.yield-offer-notice {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
