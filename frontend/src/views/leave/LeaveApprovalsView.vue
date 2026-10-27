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

<!-- Leave approvals: requests from the caller's reports, plus the HR
     queue for holders of leave:approve. A list beside the selected request
     on wide screens; on narrow ones the request opens under its row. -->
<template>
  <LeavePage title="Approvals" :subtitle="subtitle">
    <template #actions>
      <AppPillToggle :model-value="store.status" :options="TABS" aria-label="Show" @update:model-value="store.fetch" />
    </template>

    <ApprovalFilters />
    <v-progress-linear v-if="store.loading" indeterminate color="primary" />
    <AppCallout v-if="store.error" variant="error">{{ store.error }}</AppCallout>
    <AppCallout v-if="store.notice" variant="info">{{ store.notice }}</AppCallout>
    <AppCallout v-if="showLimitHint" variant="info">
      Showing the latest {{ store.items.length }} decisions.
      {{ dated ? 'Narrow the dates or filters to see the rest.' : 'Pick dates to find older ones.' }}
    </AppCallout>

    <div v-if="!store.loading && !store.error && !store.items.length" class="empty">
      <div class="empty__title">{{ emptyTitle }}</div>
      <div class="empty__text">
        {{ store.status === 'pending' ? 'New requests show here.' : 'Requests approved or rejected recently show here.' }}
      </div>
    </div>

    <div v-if="store.items.length" class="queue">
      <section class="queue__list" aria-label="Requests">
        <ul>
          <li v-for="item in store.items" :key="item.request.id">
            <ApprovalQueueItem
              :item="item"
              :selected="isOpen(item)"
              :controls="narrow ? `approval-${item.request.id}` : null"
              @select="select(item)"
            />
            <ApprovalCard v-if="narrow && isOpen(item)" :id="`approval-${item.request.id}`" :item="item" class="queue__inline" />
          </li>
        </ul>
      </section>
      <ApprovalCard v-if="!narrow && current" ref="detail" :key="current.request.id" :item="current" />
    </div>
  </LeavePage>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import ApprovalCard from '@/components/leave/ApprovalCard.vue'
import ApprovalFilters from '@/components/leave/ApprovalFilters.vue'
import ApprovalQueueItem from '@/components/leave/ApprovalQueueItem.vue'
import LeavePage from '@/components/leave/LeavePage.vue'
import { useDebounced } from '@/composables/useDebounced'
import { type ApprovalTab, useLeaveApprovalsStore } from '@/stores/leaveApprovals'
import type { ApprovalItem } from '@/types/leave'
import { queueSummary } from '@/utils/approvalFacts'

const store = useLeaveApprovalsStore()
// Before the filter bar sets up, so it never shows another viewer's picks.
store.forgetPreviousViewer()
const TABS: { label: string; value: ApprovalTab }[] = [
  { label: 'Pending', value: 'pending' },
  { label: 'Decided', value: 'decided' },
]

// Below this the sidebar leaves too little room for the list beside a request.
const NARROW_BELOW_PX = 1180
const { width } = useDisplay()
const narrow = computed(() => width.value < NARROW_BELOW_PX)

// Wide screens always show one request, the first by default; narrow ones
// open a request only when its row is tapped, and tapping again closes it.
const selectedId = ref<string | null>(null)
const current = computed(
  () => store.items.find(i => i.request.id === selectedId.value) ?? store.items[0] ?? null,
)
function isOpen(item: ApprovalItem): boolean {
  return narrow.value ? item.request.id === selectedId.value : item === current.value
}
const detail = ref<InstanceType<typeof ApprovalCard> | null>(null)

async function select(item: ApprovalItem): Promise<void> {
  const id = item.request.id
  selectedId.value = narrow.value && selectedId.value === id ? null : id
  if (narrow.value) return
  // Beside the list, a pick takes keyboard and screen-reader users to it.
  await nextTick()
  detail.value?.focusHeading()
}

const subtitle = computed(() => {
  if (store.status === 'decided') return 'Requests decided recently, newest first.'
  if (store.error || (store.loading && !store.items.length)) return ''
  return queueSummary(store.items, new Date(), filtered.value) || 'Nothing is waiting on you.'
})

const filtered = computed(() => Object.values(store.filters).some(Boolean))
const emptyTitle = computed(() => {
  if (filtered.value) return 'Nothing matches these filters'
  return store.status === 'pending' ? "You're all caught up" : 'No decisions yet'
})
// The cap applies with or without dates; dates only lift the 90-day window.
const dated = computed(() => !!(store.filters.start || store.filters.end))
const showLimitHint = computed(() => store.status === 'decided' && store.truncated)

// One request per settled change, not one per keystroke in a custom date.
const query = ref('')
const settled = useDebounced(query)
watch(
  () => JSON.stringify(store.filters),
  value => {
    query.value = value
  },
)
watch(settled, () => {
  void store.fetch()
})

onMounted(() => {
  void store.fetch()
})
</script>

<style scoped>
.queue {
  display: grid;
  grid-template-columns: minmax(300px, 400px) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.queue__list {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  overflow: hidden;
  min-width: 0;
}
.queue__list ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.queue__list li + li {
  border-top: 1px solid var(--color-rule-2);
}
.queue__inline {
  border-width: 1px 0 0;
  border-radius: 0;
}
.empty {
  text-align: center;
  padding: 48px 16px;
}
.empty__title {
  font-size: var(--text-base);
  font-weight: 500;
}
.empty__text {
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (max-width: 1179px) {
  .queue {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
