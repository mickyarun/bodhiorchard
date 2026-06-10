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
  <!-- Yield-offer reject confirmation. Reject is no-undo; the modal
       guards against misclicks. Accept fires immediately because it's
       a reversible action (a developer can re-request assignment). -->
  <v-dialog v-model="rejectDialogOpen" max-width="400">
    <v-card color="surface" class="pa-5">
      <div class="text-h6 font-weight-bold mb-2">Reject this yield offer?</div>
      <div class="text-body-2 text-medium-emphasis mb-4">
        The BUD will go to the next candidate. You can't undo this.
      </div>
      <v-card-actions class="pa-0">
        <v-spacer />
        <v-btn variant="text" @click="closeReject">Cancel</v-btn>
        <v-btn color="error" variant="flat" :loading="!!busy" @click="confirmReject">
          Reject
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Admin reassign: route a pending offer to a different developer.
       Backend validates the new target holds a strictly lower-priority
       BUD and swaps yieldable_bud_id in lockstep. -->
  <v-dialog v-model="reassignDialogOpen" max-width="440">
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
        <v-btn variant="text" @click="closeReassign">Cancel</v-btn>
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
import { computed, onUnmounted } from 'vue'
import { useMembersStore } from '@/stores/members'
import { useYieldOfferActions } from '@/composables/useYieldOfferActions'

const {
  busy,
  rejectDialogOpen,
  reassignDialogOpen,
  pendingReassign,
  reassignTargetId,
  confirmReject,
  closeReject,
  confirmReassign,
  closeReassign,
} = useYieldOfferActions()

const membersStore = useMembersStore()

// State backing these dialogs lives at module scope, so it would
// otherwise outlive a logout (this component is gated on
// authStore.user?.id). Resetting on unmount keeps a freshly-logged-in
// second user from inheriting the previous session's pending target.
onUnmounted(() => {
  closeReject()
  closeReassign()
})

// Member list is loaded by NotificationBell when the viewer is an admin;
// we just read from it. Excluding the current target keeps the picker
// from offering a no-op reassignment.
const reassignTargets = computed(() => {
  const exclude = pendingReassign.value?.target_user_id ?? ''
  return membersStore.members
    .filter(m => m.isActive && m.role === 'developer' && m.id !== exclude)
    .map(m => ({ id: m.id, name: m.name }))
})
</script>
