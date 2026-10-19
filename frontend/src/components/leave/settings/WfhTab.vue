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

<!-- How work-from-home requests are approved on this policy. -->
<template>
  <v-form class="d-flex flex-column ga-4 wfh" @submit.prevent="save">
    <v-select v-model="draft.wfh_approval" :items="MODES" label="Approval" v-bind="field" />
    <v-text-field
      v-if="draft.wfh_approval === 'auto_within_allowance'"
      v-model.number="draft.wfh_monthly_auto_days"
      label="Days a month approved automatically"
      type="number"
      min="0"
      max="31"
      hint="Requests past this go to the approver."
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
import type { WfhApproval } from '@/types/leave'
import type { PolicyRead } from '@/types/leavePolicy'
import { selectItems } from '@/utils/employee'
import { WFH_APPROVAL_LABELS } from '@/utils/leave'

const props = defineProps<{ policy: PolicyRead }>()

const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const MODES = selectItems<WfhApproval>(WFH_APPROVAL_LABELS)
const { draft, saving, error, saved, save } = usePolicyDraft(toRef(props, 'policy'))
</script>

<style scoped>
.wfh {
  max-width: 420px;
}
</style>
