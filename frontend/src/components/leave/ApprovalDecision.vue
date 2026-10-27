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

<!-- Decide a pending request: Approve as the one primary action and Reject
     as an outlined one. The note is only for a rejection, and it's needed so
     the requester knows why; approving sends no note. -->
<template>
  <div class="decision">
    <v-textarea
      ref="noteField"
      v-model="note"
      label="Reason for rejecting"
      :hint="`Needed only to reject. ${name} sees it.`"
      :error-messages="noteError"
      persistent-hint
      rows="2"
      auto-grow
      counter="500"
      maxlength="500"
      variant="outlined"
      density="compact"
      hide-details="auto"
    />
    <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
    <div class="decision__actions">
      <v-btn variant="outlined" color="error" :disabled="busy !== null" :loading="busy === 'reject'" @click="reject">
        Reject
      </v-btn>
      <v-btn color="primary" variant="flat" :disabled="busy !== null" :loading="busy === 'approve'" @click="approve">
        Approve
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useLeaveApprovalsStore } from '@/stores/leaveApprovals'
import type { LeaveRequestRead } from '@/types/leave'
import { firstName } from '@/utils/leave'

const props = defineProps<{ request: LeaveRequestRead }>()

const store = useLeaveApprovalsStore()
const note = ref('')
const noteError = ref('')
const error = ref('')
const busy = ref<'approve' | 'reject' | null>(null)
const noteField = ref<{ focus: () => void } | null>(null)
const name = computed(() => firstName(props.request.user.name))

// A different request in the same panel starts clean.
watch(
  () => props.request.id,
  () => {
    note.value = ''
    noteError.value = ''
    error.value = ''
  },
)
watch(note, () => {
  noteError.value = ''
})

async function run(action: 'approve' | 'reject'): Promise<void> {
  busy.value = action
  error.value =
    (action === 'approve'
      ? await store.approve(props.request.id, '')
      : await store.reject(props.request.id, note.value)) ?? ''
  busy.value = null
}

function approve(): Promise<void> {
  noteError.value = ''
  return run('approve')
}

function reject(): Promise<void> | void {
  if (!note.value.trim()) {
    noteError.value = `Add a note so ${name.value} knows why.`
    noteField.value?.focus()
    return
  }
  return run('reject')
}
</script>

<style scoped>
.decision {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 18px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
.decision__actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
