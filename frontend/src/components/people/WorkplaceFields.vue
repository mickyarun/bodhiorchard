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

<!-- Work arrangement plus office, for the employment form and the add
     dialog. Remote people have no office, so the picker hides and clears.
     An office with a leave policy moves the person onto it on save. -->
<template>
  <v-select
    :model-value="arrangement"
    :items="ARRANGEMENTS"
    label="Work arrangement"
    v-bind="FIELD"
    @update:model-value="setArrangement"
  />
  <v-select
    v-if="arrangement !== 'remote'"
    :model-value="officeId"
    :items="officeItems"
    label="Office"
    clearable
    :loading="store.loading"
    :hint="policyHint"
    :persistent-hint="!!policyHint"
    :no-data-text="emptyText"
    v-bind="FIELD"
    @update:model-value="emit('update:officeId', $event ?? null)"
  />
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useOfficesStore } from '@/stores/offices'
import type { WorkArrangement } from '@/types/employee'
import { ARRANGEMENT_LABELS, selectItems } from '@/utils/employee'

const props = defineProps<{ arrangement: WorkArrangement; officeId: string | null }>()
const emit = defineEmits<{
  'update:arrangement': [value: WorkArrangement]
  'update:officeId': [value: string | null]
}>()

const FIELD = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const ARRANGEMENTS = selectItems(ARRANGEMENT_LABELS)
const store = useOfficesStore()

const officeItems = computed(() => store.offices.map(o => ({ title: o.name, value: o.id })))
const emptyText = computed(() => store.error || 'No offices yet. Add them in Settings → Offices.')

const policyHint = computed(() => {
  const office = store.offices.find(o => o.id === props.officeId)
  return office?.leave_policy_name ? `Follows the ${office.leave_policy_name} leave policy.` : ''
})

function setArrangement(value: WorkArrangement): void {
  emit('update:arrangement', value)
  if (value === 'remote') emit('update:officeId', null)
}

onMounted(() => void store.fetchOffices())
</script>
