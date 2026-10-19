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

<!-- How someone who joins (or moves onto this policy) mid-year is allocated leave. -->
<template>
  <v-form class="d-flex flex-column ga-4 joiners" @submit.prevent="save">
    <p class="text-body-2 text-medium-emphasis">
      Someone who joins, or moves onto this policy, after the leave year starts gets a share of each
      leave type's quota. A year's allocation is fixed the first time they request leave in it, so
      changes here apply to people who haven't yet.
    </p>
    <v-select v-model="draft.proration_method" :items="METHODS" label="Prorate" v-bind="field" />
    <v-text-field
      v-if="draft.proration_method === 'monthly'"
      v-model.number="draft.proration_cutoff_day"
      label="Joining month counts if they join on or before day"
      type="number"
      min="1"
      max="31"
      hint="E.g. 15: joining on the 15th counts that month, the 16th doesn't."
      persistent-hint
      v-bind="field"
    />
    <v-select
      v-if="draft.proration_method !== 'none'"
      v-model="draft.allocation_rounding"
      :items="ROUNDINGS"
      label="Round the result"
      hint="Never rounds above the full quota."
      persistent-hint
      v-bind="field"
    />
    <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
    <AppCallout v-else-if="saved" variant="success">Saved.</AppCallout>
    <div>
      <v-btn type="submit" color="primary" :loading="saving">Save</v-btn>
    </div>
  </v-form>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { usePolicyDraft } from '@/composables/usePolicyDraft'
import type { AllocationRounding, PolicyRead, ProrationMethod } from '@/types/leavePolicy'
import { selectItems } from '@/utils/employee'
import { PRORATION_LABELS, ROUNDING_LABELS } from '@/utils/leavePolicy'

const props = defineProps<{ policy: PolicyRead }>()

const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const METHODS = selectItems<ProrationMethod>(PRORATION_LABELS)
const ROUNDINGS = selectItems<AllocationRounding>(ROUNDING_LABELS)
const { draft, saving, error, saved, save } = usePolicyDraft(toRef(props, 'policy'))
</script>

<style scoped>
.joiners {
  max-width: 480px;
}
</style>
