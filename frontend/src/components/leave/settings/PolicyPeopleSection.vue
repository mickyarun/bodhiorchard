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

<!-- Who follows this policy, adding people to it, and moving them off. -->
<template>
  <LeaveSectionCard icon="mdi-account-multiple-outline" title="People" :caption="caption">
    <template #actions>
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-account-plus-outline" @click="adding = true">
        Add people
      </v-btn>
    </template>
    <AppCallout v-if="notice" :variant="notice.variant" class="mb-4">{{ notice.text }}</AppCallout>
    <LeaveAssignmentsTable :pinned-policy-id="policy.id" />
    <PolicyAddPeopleDialog v-model="adding" :policy="policy" @moved="onMoved" />
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveAssignmentsTable from '@/components/leave/settings/LeaveAssignmentsTable.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import PolicyAddPeopleDialog from '@/components/leave/settings/PolicyAddPeopleDialog.vue'
import type { AssignResult, PolicyRead } from '@/types/leavePolicy'
import { movedSummary, movedVariant } from '@/utils/leavePolicy'

const props = defineProps<{ policy: PolicyRead }>()

const adding = ref(false)
const notice = ref<{ text: string; variant: 'success' | 'warning' } | null>(null)
const caption = computed(() =>
  props.policy.is_default
    ? "Everyone you haven't assigned to another policy follows this one."
    : 'People assigned to this policy. Select people to move them to another one.',
)

function onMoved(result: AssignResult): void {
  notice.value = { text: movedSummary(result, props.policy.name), variant: movedVariant(result) }
}
</script>
