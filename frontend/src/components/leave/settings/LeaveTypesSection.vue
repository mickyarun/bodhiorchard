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

<!-- A policy's leave types. Switched-off types sit apart: they can't be
     requested any more, but their past requests and balances stay. -->
<template>
  <LeaveSectionCard
    icon="mdi-shape-outline"
    title="Leave types"
    caption="What people on this policy can request, and how many days they get each leave year."
  >
    <template v-if="store.types.length" #actions>
      <v-btn v-if="!hasWomenOnlyType(store.types)" variant="text" prepend-icon="mdi-water-outline" @click="addPeriodLeave">
        Add period leave
      </v-btn>
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="edit(null)">Add leave type</v-btn>
    </template>
    <AppCallout v-if="store.typesError" variant="error" class="mb-4">{{ store.typesError }}</AppCallout>
    <LeaveEmptyState
      v-if="!store.types.length && !store.typesError"
      icon="mdi-shape-plus-outline"
      title="No leave types yet"
      body="Add the leave people can request, such as casual, sick or parental."
    >
      <template #actions>
        <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="edit(null)">Add leave type</v-btn>
        <v-btn variant="text" prepend-icon="mdi-water-outline" @click="addPeriodLeave">Add period leave</v-btn>
      </template>
    </LeaveEmptyState>
    <template v-else>
      <LeaveTypeTable v-if="groups.active.length" :types="groups.active" @edit="edit" />
      <div v-if="groups.inactive.length" class="mt-4">
        <v-btn
          variant="text"
          size="small"
          :append-icon="showOff ? 'mdi-chevron-up' : 'mdi-chevron-down'"
          :aria-expanded="showOff"
          @click="showOff = !showOff"
        >
          Switched off ({{ groups.inactive.length }})
        </v-btn>
        <v-expand-transition>
          <LeaveTypeTable v-if="showOff" :types="groups.inactive" class="mt-2" @edit="edit" />
        </v-expand-transition>
      </div>
    </template>
    <LeaveTypeDialog v-model="dialogOpen" :policy-id="policy.id" :policy-name="policy.name" :type="editing" :preset="preset" />
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import LeaveTypeDialog from '@/components/leave/settings/LeaveTypeDialog.vue'
import LeaveTypeTable from '@/components/leave/settings/LeaveTypeTable.vue'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { LeaveTypeRead, LeaveTypeWrite, PolicyRead } from '@/types/leavePolicy'
import { splitLeaveTypes } from '@/utils/leavePolicyDisplay'
import { hasWomenOnlyType, periodLeave } from '@/utils/leaveTypeDraft'

const props = defineProps<{ policy: PolicyRead }>()

const store = useLeavePolicyConfigStore()
const dialogOpen = ref(false)
const editing = ref<LeaveTypeRead | null>(null)
const preset = ref<LeaveTypeWrite | null>(null)
const showOff = ref(false)
const groups = computed(() => splitLeaveTypes(store.types))

function edit(type: LeaveTypeRead | null): void {
  editing.value = type
  preset.value = null
  dialogOpen.value = true
}

/** Opens the dialog filled in for period leave; HR reviews and saves it. */
function addPeriodLeave(): void {
  editing.value = null
  preset.value = periodLeave()
  dialogOpen.value = true
}

watch(
  () => props.policy.id,
  id => {
    showOff.value = false
    void store.fetchTypes(id)
  },
  { immediate: true },
)
</script>
