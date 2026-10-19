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

<!-- Re-run a frozen year's allocation for one member (leave:configure).
     Use after fixing a joining date or the policy's proration rule. -->
<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="emit('update:modelValue', $event)">
    <v-card class="pa-0">
      <div class="d-flex align-center justify-space-between pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">Recalculate allocation</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <div class="px-6 d-flex flex-column ga-3">
        <p class="text-body-2 text-medium-emphasis">
          A year's allocation is fixed the first time leave is requested in it. If their joining
          date or the policy's new joiner rules changed since, this books the difference as a
          correction in the ledger.
        </p>
        <v-select v-model="typeId" :items="typeItems" label="Leave type" v-bind="field" />
        <AppCallout v-if="outcome" variant="success">{{ outcome }}</AppCallout>
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </div>
      <div class="d-flex justify-end ga-2 pa-6 pt-4">
        <v-btn variant="text" @click="close">{{ outcome ? 'Done' : 'Cancel' }}</v-btn>
        <v-btn v-if="!outcome" color="primary" :loading="saving" :disabled="!typeId" @click="submit">
          Recalculate
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import type { Balance } from '@/types/leave'
import type { Recalculate, RecalculateResult } from '@/types/leavePolicy'
import { recalculationSummary } from '@/utils/leaveConfigHistory'

const props = defineProps<{
  modelValue: boolean
  balances: Balance[]
  leaveYear: number
  recalculate: (body: Recalculate) => Promise<RecalculateResult | string>
}>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const typeId = ref<string | null>(null)
const saving = ref(false)
const error = ref('')
const outcome = ref('')

// Unlimited types have no allocation to recalculate.
const typeItems = computed(() =>
  props.balances
    .filter(b => b.allocated !== null)
    .map(b => ({ title: b.leave_type.name, value: b.leave_type.id })),
)

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    typeId.value = typeItems.value[0]?.value ?? null
    error.value = ''
    outcome.value = ''
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!typeId.value) return
  saving.value = true
  const result = await props.recalculate({ leave_type_id: typeId.value, leave_year: props.leaveYear })
  saving.value = false
  if (typeof result === 'string') {
    error.value = result
    return
  }
  error.value = ''
  outcome.value = recalculationSummary(result)
}
</script>
