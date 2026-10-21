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

<!-- Labelled facts under an approval: the requester's last leave, the
     balance after approval when the request is in another leave year, and
     teammates out on the same days. -->
<template>
  <dl v-if="facts.length" class="facts text-body-2">
    <template v-for="fact in facts" :key="fact.label">
      <dt class="text-medium-emphasis"><v-icon :icon="fact.icon" size="16" class="mr-1" />{{ fact.label }}</dt>
      <dd>{{ fact.text }}</dd>
    </template>
  </dl>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ApprovalItem } from '@/types/leave'
import { lastLeaveLine, otherYearBalanceAfter } from '@/utils/approvalFacts'
import { firstName, formatDays } from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'

const props = defineProps<{ item: ApprovalItem }>()

interface Fact {
  label: string
  icon: string
  text: string
}

const facts = computed(() => {
  const list: Fact[] = []
  const request = props.item.request
  if (request.status === 'pending' && request.kind === 'leave') {
    const last = props.item.last_leave
    list.push({
      label: 'Last leave',
      icon: 'mdi-history',
      text: last ? lastLeaveLine(last, new Date()) : 'None taken yet',
    })
  }
  const after = otherYearBalanceAfter(props.item)
  if (after !== null) {
    list.push({ label: 'Left after this', icon: 'mdi-scale-balance', text: `${formatDays(after)} in its leave year` })
  }
  if (props.item.also_out.length) {
    const names = props.item.also_out.map(o => `${firstName(o.name)} (${formatDayRange(o.start_date, o.end_date)})`)
    list.push({ label: 'Also out', icon: 'mdi-account-group-outline', text: names.join(', ') })
  }
  return list
})
</script>

<style scoped>
.facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 6px 16px;
  margin: 0;
}
.facts dt {
  display: flex;
  align-items: center;
}
.facts dd {
  margin: 0;
}
</style>
