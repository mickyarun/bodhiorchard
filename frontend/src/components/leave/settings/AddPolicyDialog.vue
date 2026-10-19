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

<!-- Create a leave policy: where it applies, working days and when the
     leave year starts. Types and holidays are added after. -->
<template>
  <v-dialog :model-value="modelValue" max-width="600" :fullscreen="xs" @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" rounded="lg">
      <div class="d-flex align-start ga-2 pa-6 pb-4">
        <div class="flex-grow-1">
          <h2 class="text-h6 font-weight-bold">Add policy</h2>
          <p class="text-body-2 text-medium-emphasis">
            Usually one per country or office. Add leave types and holidays next.
          </p>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6 pb-2 d-flex flex-column ga-5" @submit.prevent="submit">
        <PolicyDetailsFields
          v-model:name="draft.name"
          v-model:country="draft.country_code"
          v-model:subdivision="draft.subdivision_code"
          v-model:timezone="draft.timezone"
        />
        <LeaveFormGrid>
          <v-select v-model="draft.year_start_month" :items="MONTH_ITEMS" label="Leave year starts in" v-bind="FIELD_PROPS" />
        </LeaveFormGrid>
        <WorkingDayChips v-model="draft.working_days" />
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </v-form>
      <v-divider class="mt-4" />
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="submit">
          Create policy
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveFormGrid from '@/components/leave/settings/LeaveFormGrid.vue'
import PolicyDetailsFields from '@/components/leave/settings/PolicyDetailsFields.vue'
import WorkingDayChips from '@/components/leave/settings/WorkingDayChips.vue'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { PolicyRead, PolicyWrite } from '@/types/leavePolicy'
import { MONTH_ITEMS, newPolicy } from '@/utils/leavePolicy'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; created: [policy: PolicyRead] }>()

const store = useLeavePoliciesStore()
const { xs } = useDisplay()
const draft = ref<PolicyWrite>(newPolicy())
const saving = ref(false)
const error = ref('')
const valid = computed(() => !!draft.value.name.trim() && !!draft.value.timezone)

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    draft.value = newPolicy()
    error.value = ''
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!valid.value) return
  saving.value = true
  const result = await store.createPolicy({ ...draft.value, name: draft.value.name.trim() })
  saving.value = false
  if (typeof result === 'string') {
    error.value = result
    return
  }
  emit('created', result)
  close()
}
</script>
