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

<!-- The bug list: title (opens the bug), severity, status, the BUD it's
     linked to, when it was reported and who owns it. On phones each row
     stacks into a small card. -->
<template>
  <section class="bug-table" :aria-label="label">
    <table>
      <thead>
        <tr>
          <th scope="col">Bug</th>
          <th scope="col">Severity</th>
          <th scope="col">Status</th>
          <th scope="col">Linked BUD</th>
          <th scope="col">Reported</th>
          <th scope="col">Owner</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="bug in bugs" :key="bug.id">
          <td class="bug-table__bug">
            <button type="button" class="bug-table__title" @click="emit('open', bug)">{{ bug.title }}</button>
            <span class="bug-table__sub">{{ [bugRef(bug.bugNumber), bugWhere(bug)].filter(Boolean).join(' · ') }}</span>
          </td>
          <td>
            <AppTag :color="BUG_SEVERITY_COLORS[bug.severity]" sr-prefix="Severity:">{{ severityLabel(bug.severity) }}</AppTag>
          </td>
          <td>
            <AppTag :color="BUG_STATUS_COLORS[bug.status] ?? 'muted'" sr-prefix="Status:">
              {{ BUG_STATUS_LABELS[bug.status] ?? bug.status }}
            </AppTag>
          </td>
          <td>
            <router-link v-if="bug.budId && bug.budNumber" :to="`/buds/${bug.budId}`" class="bug-table__bud">
              {{ budRef(bug.budNumber) }}
            </router-link>
            <span v-else class="bug-table__muted">Not linked</span>
          </td>
          <td class="bug-table__when" :title="formatDateTime(bug.createdAt)">
            <span class="bug-table__cell-label">Reported </span>{{ relativeTime(bug.createdAt, now) }}
          </td>
          <td :class="{ 'bug-table__muted': !bug.assigneeName }">{{ bug.assigneeName || 'Unassigned' }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import AppTag from '@/components/common/AppTag.vue'
import { BUG_SEVERITY_COLORS, BUG_STATUS_COLORS, BUG_STATUS_LABELS, budRef, type BugListItem } from '@/types'
import { bugRef, bugWhere, severityLabel } from '@/utils/bugList'
import { formatDateTime, relativeTime } from '@/utils/date'

defineProps<{ bugs: BugListItem[]; label: string; now: Date }>()
const emit = defineEmits<{ open: [bug: BugListItem] }>()
</script>

<style scoped>
.bug-table {
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
th {
  padding: 11px 12px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface-variant));
  background: rgb(var(--v-theme-background));
}
td {
  padding: 14px 12px;
  vertical-align: top;
  color: rgb(var(--v-theme-ink-2));
}
th:first-child,
td:first-child {
  padding-left: 20px;
}
tbody tr {
  border-top: 1px solid rgb(var(--v-theme-rule));
}
.bug-table__bug {
  min-width: 0;
}
.bug-table__title {
  display: block;
  padding: 0;
  text-align: left;
  font: inherit;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  overflow-wrap: anywhere;
}
.bug-table__title:hover {
  color: var(--color-accent-text);
  text-decoration: underline;
}
.bug-table__sub,
.bug-table__muted {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
td.bug-table__muted {
  font-size: 14px;
}
.bug-table__bud {
  font: 500 12px var(--font-mono);
  color: var(--color-accent-text);
  text-decoration: none;
}
.bug-table__bud:hover {
  text-decoration: underline;
}
.bug-table__when {
  white-space: nowrap;
}
.bug-table__cell-label {
  display: none;
}
/* Phones: each row becomes a card; the column headings give way to the
   tags and a "Reported" prefix. */
@media (max-width: 760px) {
  thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  tbody tr {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
    padding: 14px 16px;
  }
  tbody tr:first-child {
    border-top: 0;
  }
  td,
  td:first-child {
    padding: 0;
    font-size: 13px;
  }
  .bug-table__bug {
    flex-basis: 100%;
  }
  .bug-table__cell-label {
    display: inline;
  }
}
</style>
