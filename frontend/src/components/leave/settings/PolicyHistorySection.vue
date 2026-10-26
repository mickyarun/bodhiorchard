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

<!-- Who changed this policy and its leave types, newest first. Read-only:
     the trail can't be edited or deleted. Loads each time it's shown, so
     a change made in another section is already here. -->
<template>
  <LeaveSectionCard
    icon="mdi-history"
    title="History"
    caption="Every change to this policy and its leave types, and who made it."
  >
    <v-progress-linear v-if="history.loading.value" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="history.error.value" variant="error" class="mb-4">{{ history.error.value }}</AppCallout>
    <LeaveEmptyState
      v-else-if="!history.loading.value && !history.events.value.length"
      icon="mdi-history"
      title="No changes yet"
      body="Edits to this policy, its leave types and who follows it show here, with who made them."
    />
    <ConfigEventList :events="history.events.value" />
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import ConfigEventList from '@/components/leave/settings/ConfigEventList.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import { useConfigHistory } from '@/composables/useConfigHistory'

const props = defineProps<{ policyId: string }>()
const history = useConfigHistory()

watch(() => props.policyId, id => void history.load(`/v1/leave/policies/${id}/history`), {
  immediate: true,
})
</script>
