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

<!-- Confirm moving the selected people onto a policy from today. -->
<template>
  <v-dialog v-model="open" max-width="520">
    <v-card color="surface" rounded="lg">
      <div class="pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">{{ policy ? moveTitle(userIds.length, policy.name) : '' }}</h2>
        <p class="text-body-2 text-medium-emphasis mt-2">{{ MOVE_POLICY_BODY }}</p>
        <AppCallout v-if="error" variant="error" class="mt-4">{{ error }}</AppCallout>
      </div>
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" :disabled="moving" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="moving" :disabled="!policy || !userIds.length" @click="confirm">
          Move {{ peopleCount(userIds.length) }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useLeaveAssignmentsStore } from '@/stores/leaveAssignments'
import type { AssignResult } from '@/types/leavePolicy'
import { peopleCount } from '@/utils/leavePolicyDisplay'
import { MOVE_POLICY_BODY, moveTitle } from '@/utils/policyMembers'

const props = defineProps<{ policy: { id: string; name: string } | null; userIds: string[] }>()
const emit = defineEmits<{ moved: [result: AssignResult] }>()
const open = defineModel<boolean>({ required: true })

const store = useLeaveAssignmentsStore()
const moving = ref(false)
const error = ref('')

watch(open, isOpen => {
  if (isOpen) error.value = ''
})

async function confirm(): Promise<void> {
  if (!props.policy || !props.userIds.length) return
  moving.value = true
  const result = await store.move(props.policy.id, props.userIds)
  moving.value = false
  if (typeof result === 'string') {
    error.value = result
    return
  }
  open.value = false
  emit('moved', result)
}
</script>
