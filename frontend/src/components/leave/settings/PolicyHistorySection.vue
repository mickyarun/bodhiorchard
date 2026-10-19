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
    <ol class="history">
      <li v-for="event in history.events.value" :key="event.id" class="py-3">
        <div class="text-body-2">
          <strong>{{ event.actor.name }}</strong> · {{ eventTitle(event) }}
        </div>
        <ul v-if="changeLines(event.changes).length" class="text-body-2 text-medium-emphasis mt-1">
          <li v-for="line in changeLines(event.changes)" :key="line">{{ line }}</li>
        </ul>
        <div class="text-caption text-medium-emphasis mt-1">{{ formatDateTime(event.at) }}</div>
      </li>
    </ol>
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import { usePolicyHistory } from '@/composables/usePolicyHistory'
import { formatDateTime } from '@/utils/date'
import { changeLines, eventTitle } from '@/utils/leaveConfigHistory'

const props = defineProps<{ policyId: string }>()
const history = usePolicyHistory()

watch(() => props.policyId, id => void history.load(id), { immediate: true })
</script>

<style scoped>
.history {
  list-style: none;
  padding: 0;
}
.history > li + li {
  border-top: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}
.history ul {
  padding-left: 18px;
}
</style>
