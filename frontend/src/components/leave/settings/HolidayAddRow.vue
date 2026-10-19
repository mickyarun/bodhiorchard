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

<!-- Add one holiday to the year shown. Stays open after adding, so a few
     can be entered in a row. -->
<template>
  <div>
    <v-form class="add-row" aria-label="Add a holiday" @submit.prevent="submit">
      <v-text-field
        v-model="date"
        label="Date"
        type="date"
        :min="`${year}-01-01`"
        :max="`${year}-12-31`"
        autofocus
        v-bind="FIELD_PROPS"
      />
      <v-text-field v-model="name" label="Holiday name" maxlength="150" v-bind="FIELD_PROPS" />
      <AppPillToggle v-model="kind" :options="HOLIDAY_KIND_OPTIONS" size="sm" aria-label="Mandatory or optional" />
      <div class="d-flex ga-1">
        <v-btn type="submit" color="primary" variant="flat" :loading="saving" :disabled="!date || !name.trim()">Add</v-btn>
        <v-btn variant="text" @click="emit('close')">Done</v-btn>
      </div>
    </v-form>
    <AppCallout v-if="error" variant="error" class="mt-2">{{ error }}</AppCallout>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { HolidayKind } from '@/types/leave'
import { HOLIDAY_KIND_OPTIONS } from '@/utils/leavePolicy'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const props = defineProps<{ policyId: string; year: number }>()
const emit = defineEmits<{ close: [] }>()

const store = useLeavePolicyConfigStore()
const date = ref('')
const name = ref('')
const kind = ref<HolidayKind>('mandatory')
const saving = ref(false)
const error = ref('')

async function submit(): Promise<void> {
  if (!date.value || !name.value.trim()) return
  saving.value = true
  error.value =
    (await store.addHoliday(props.policyId, {
      date: date.value,
      name: name.value.trim(),
      kind: kind.value,
    })) ?? ''
  saving.value = false
  if (error.value) return
  date.value = ''
  name.value = ''
  kind.value = 'mandatory'
}
</script>

<style scoped>
.add-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
}
@media (max-width: 720px) {
  .add-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
