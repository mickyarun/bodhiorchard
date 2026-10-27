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

<!-- The BUD's facts at a glance: owner, priority, complexity, forecast,
     the branch prefix commits go on, and the repositories it touches. -->
<template>
  <AppPanel title="Details">
    <dl class="bud-facts">
      <dt>Assignee</dt>
      <dd class="bud-facts__split">
        <span>{{ bud.assignee_name || 'Unassigned' }}</span>
        <BUDAssigneeMenu :assignee-id="bud.assignee_id" @change="emit('change-assignee', $event)">
          <template #activator="{ props: menuProps }">
            <button v-bind="menuProps" type="button" class="bud-facts__link" aria-label="Change assignee">Change</button>
          </template>
        </BUDAssigneeMenu>
      </dd>
      <dt>Priority</dt>
      <dd><BudPriorityChip :priority="bud.priority" /></dd>
      <dt>Complexity</dt>
      <dd>{{ bud.complexity ? `${bud.complexity} of 5` : 'Not rated yet' }}</dd>
      <dt>Estimate</dt>
      <dd>
        <template v-if="bud.prod_p70_date">
          Prod by {{ formatDate(bud.prod_p70_date) }} <span class="bud-facts__muted">· 70%</span>
        </template>
        <span v-else class="bud-facts__muted">No forecast yet</span>
      </dd>
      <dt>Branch</dt>
      <dd class="bud-facts__branch">
        <code>{{ branchPrefix(bud.bud_number) }}</code>
        <v-btn
          :icon="copied ? 'mdi-check' : 'mdi-content-copy'"
          variant="outlined"
          size="x-small"
          class="bud-facts__copy"
          :aria-label="copied ? 'Branch prefix copied' : 'Copy branch prefix'"
          @click="copyBranch"
        />
      </dd>
      <dt>Repositories</dt>
      <dd class="bud-facts__repos">
        <code v-for="r in bud.impacted_repos ?? []" :key="r.repo_id">{{ r.repo_name }}</code>
        <span v-if="!bud.impacted_repos?.length" class="bud-facts__muted">None linked yet</span>
      </dd>
    </dl>
  </AppPanel>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import BudPriorityChip from '@/components/buds/BudPriorityChip.vue'
import BUDAssigneeMenu from './BUDAssigneeMenu.vue'
import type { BUDDocument } from '@/types'
import { branchPrefix } from '@/utils/budDetail'
import { formatDate } from '@/utils/date'

const props = defineProps<{ bud: BUDDocument }>()
const emit = defineEmits<{ 'change-assignee': [memberId: string | null] }>()

const copied = ref(false)
let resetTimer: ReturnType<typeof setTimeout> | undefined

async function copyBranch(): Promise<void> {
  await navigator.clipboard.writeText(branchPrefix(props.bud.bud_number))
  copied.value = true
  clearTimeout(resetTimer)
  resetTimer = setTimeout(() => { copied.value = false }, 2000)
}
onBeforeUnmount(() => clearTimeout(resetTimer))
</script>

<style scoped>
.bud-facts {
  margin: 0;
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 12px;
  font-size: 14px;
}
.bud-facts dt {
  color: rgb(var(--v-theme-on-surface-variant));
}
.bud-facts dd {
  margin: 0;
  min-width: 0;
}
.bud-facts__split {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.bud-facts__link {
  border: 0;
  padding: 0;
  background: transparent;
  font: inherit;
  font-size: 13px;
  color: var(--color-accent-text);
  cursor: pointer;
}
.bud-facts__link:hover {
  text-decoration: underline;
}
.bud-facts__muted {
  color: rgb(var(--v-theme-on-surface-variant));
}
.bud-facts code {
  font: 500 12px var(--font-mono);
  padding: 2px 8px;
  border-radius: 6px;
  background: rgb(var(--v-theme-surface-variant));
  overflow-wrap: anywhere;
}
.bud-facts__branch,
.bud-facts__repos {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.bud-facts__copy {
  border-color: rgb(var(--v-theme-rule));
}
</style>
