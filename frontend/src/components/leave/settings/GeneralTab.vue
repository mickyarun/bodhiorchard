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

<!-- A policy's name, region, calendar rules and limits. The leave-year
     start is locked once requests exist, so past balances stay valid. -->
<template>
  <v-form class="d-flex flex-column ga-4 general" @submit.prevent="save">
    <v-text-field v-model="draft.name" label="Name" v-bind="field" />
    <RegionFields v-model:country="draft.country_code" v-model:subdivision="draft.subdivision_code" />
    <div class="form-grid">
      <v-text-field v-model="draft.timezone" label="Timezone" v-bind="field" />
      <v-select
        v-model="draft.year_start_month"
        :items="MONTH_ITEMS"
        label="Leave year starts in"
        :disabled="policy.has_requests"
        :hint="policy.has_requests ? 'Locked: people have already requested leave on this policy.' : ''"
        persistent-hint
        v-bind="field"
      />
      <v-text-field
        v-model.number="draft.backdate_limit_days"
        label="Backdate limit (days)"
        type="number"
        min="0"
        max="365"
        hint="How far back someone can request leave."
        persistent-hint
        v-bind="field"
      />
      <v-text-field
        v-model.number="draft.optional_holiday_quota"
        label="Optional holidays a year"
        type="number"
        min="0"
        max="60"
        v-bind="field"
      />
    </div>
    <WorkingDayChips v-model="draft.working_days" />
    <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
    <AppCallout v-else-if="saved" variant="success">Saved.</AppCallout>
    <div>
      <v-btn type="submit" color="primary" :loading="saving" :disabled="!draft.name.trim()">Save</v-btn>
    </div>
  </v-form>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import RegionFields from '@/components/leave/settings/RegionFields.vue'
import WorkingDayChips from '@/components/leave/settings/WorkingDayChips.vue'
import { usePolicyDraft } from '@/composables/usePolicyDraft'
import type { PolicyRead } from '@/types/leavePolicy'
import { MONTH_ITEMS } from '@/utils/leavePolicy'

const props = defineProps<{ policy: PolicyRead }>()

const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const { draft, saving, error, saved, save } = usePolicyDraft(toRef(props, 'policy'))
</script>

<style scoped>
.general {
  max-width: 640px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 600px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
