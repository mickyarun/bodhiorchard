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

<!-- The employee list: one row per person, the whole row opens their
     profile. Narrow screens drop the code, workplace and manager columns. -->
<template>
  <section class="dir-table" aria-label="Employee list">
    <v-progress-linear v-if="loading" indeterminate color="primary" />
    <div class="dir-table__scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col" class="col-code">Code</th>
            <th scope="col">Role</th>
            <th scope="col" class="col-where">Works from</th>
            <th scope="col" class="col-manager">Manager</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.user_id"
            class="dir-table__row"
            :class="{ 'dir-table__row--inactive': row.status === 'exited' || !row.is_active }"
            @click="open(row.user_id)"
          >
            <td><DirectoryPersonCell :row="row" /></td>
            <td class="col-code mono">{{ row.employee_code || '—' }}</td>
            <td>
              <div>{{ row.designation || '—' }}</div>
              <div v-if="row.department" class="muted small">{{ row.department }}</div>
            </td>
            <td class="col-where ink-2">{{ worksFromLabel(row.work_arrangement, row.office) }}</td>
            <td class="col-manager ink-2">{{ managerLabel(row) }}</td>
          </tr>
          <tr v-if="!loading && rows.length === 0">
            <td colspan="5" class="dir-table__empty">{{ emptyLabel }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <footer class="dir-table__foot">
      <span>Showing {{ rows.length }} of {{ total }}</span>
      <span>Bank details and ID numbers stay masked. Only HR and the person can reveal them.</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import DirectoryPersonCell from '@/components/people/directory/DirectoryPersonCell.vue'
import type { DirectoryEntry } from '@/types/employee'
import { worksFromLabel } from '@/utils/employeeDirectory'

defineProps<{
  rows: DirectoryEntry[]
  /** How many the search and status returned, before department/office. */
  total: number
  loading: boolean
  emptyLabel: string
}>()

const router = useRouter()

function managerLabel(row: DirectoryEntry): string {
  if (!row.primary_manager) return '—'
  const extra = row.manager_count > 1 ? ` +${row.manager_count - 1}` : ''
  return `${row.primary_manager.name}${extra}`
}

function open(userId: string): void {
  void router.push({ name: 'employee-profile', params: { userId } })
}
</script>

<style scoped>
.dir-table {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  overflow: hidden;
  min-width: 0;
}
.dir-table__scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
th {
  text-align: left;
  padding: 11px 12px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface-variant));
  background: rgb(var(--v-theme-surface-variant));
  white-space: nowrap;
}
td {
  padding: 10px 12px;
  border-top: 1px solid var(--color-rule-2);
  vertical-align: middle;
}
th:first-child,
td:first-child {
  padding-left: 20px;
}
.dir-table__row {
  cursor: pointer;
  transition: background-color var(--dur-short) ease;
}
.dir-table__row:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.dir-table__row--inactive {
  opacity: 0.55;
}
.muted {
  color: rgb(var(--v-theme-on-surface-variant));
}
.ink-2 {
  color: rgb(var(--v-theme-ink-2));
}
.col-where {
  white-space: nowrap;
}
.small {
  font-size: 12px;
  overflow-wrap: anywhere;
}
.mono {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-ink-2));
  white-space: nowrap;
}
.dir-table__empty {
  text-align: center;
  padding: 32px 20px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.dir-table__foot {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 16px;
  padding: 12px 20px;
  border-top: 1px solid var(--color-rule-2);
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (max-width: 1200px) {
  .col-code {
    display: none;
  }
}
@media (max-width: 600px) {
  .col-where,
  .col-manager {
    display: none;
  }
  th:first-child,
  td:first-child,
  .dir-table__foot {
    padding-left: 16px;
  }
}
</style>
