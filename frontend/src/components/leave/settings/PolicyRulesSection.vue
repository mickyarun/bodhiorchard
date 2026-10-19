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

<!-- A policy's rules: work week, leave year, work from home and new
     joiners. One draft for all of them, saved together from the bar that
     appears once something changes. -->
<template>
  <section aria-label="Rules">
    <WorkWeekCard v-model="draft.working_days" />
    <LeaveYearCard
      v-model:start-month="draft.year_start_month"
      v-model:backdate-days="draft.backdate_limit_days"
      v-model:optional-holidays="draft.optional_holiday_quota"
      :locked="policy.has_requests"
    />
    <WfhCard v-model:approval="draft.wfh_approval" v-model:monthly-auto-days="draft.wfh_monthly_auto_days" />
    <NewJoinersCard
      v-model:method="draft.proration_method"
      v-model:cutoff-day="draft.proration_cutoff_day"
      v-model:rounding="draft.allocation_rounding"
    />
    <AppCallout v-if="error" variant="error" class="mb-4">{{ error }}</AppCallout>
    <PolicySaveBar :visible="dirty" :saving="saving" @discard="discard" @save="submit" />

    <v-snackbar v-model="saved" :timeout="2500" location="bottom">Saved</v-snackbar>
    <ConfirmDialog
      :model-value="guard.asking.value"
      title="Discard unsaved changes?"
      message="Your changes to this policy's rules haven't been saved."
      confirm-label="Discard changes"
      cancel-label="Keep editing"
      tone="warning"
      @confirm="guard.answer(true)"
      @cancel="guard.answer(false)"
    />
  </section>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveYearCard from '@/components/leave/settings/LeaveYearCard.vue'
import NewJoinersCard from '@/components/leave/settings/NewJoinersCard.vue'
import PolicySaveBar from '@/components/leave/settings/PolicySaveBar.vue'
import WfhCard from '@/components/leave/settings/WfhCard.vue'
import WorkWeekCard from '@/components/leave/settings/WorkWeekCard.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { usePolicyDraft } from '@/composables/usePolicyDraft'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'
import type { PolicyRead } from '@/types/leavePolicy'
import { RULE_FIELDS } from '@/utils/leavePolicy'

const props = defineProps<{ policy: PolicyRead }>()

const { draft, dirty, saving, error, save, discard } = usePolicyDraft(
  toRef(props, 'policy'),
  RULE_FIELDS,
)
// Switching section, policy or view unmounts this form.
const guard = useUnsavedGuard(dirty, ['policy', 'section', 'view'])
const saved = ref(false)

async function submit(): Promise<void> {
  saved.value = await save()
}
</script>
