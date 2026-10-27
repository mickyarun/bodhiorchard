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

<!-- Team card beside the profile: their managers and, for viewers who can
     see the directory, who else shares the primary manager and who reports
     to this person. -->
<template>
  <AppPanel title="Team">
    <p v-if="!record.managers.length" class="team__empty">No manager set. Leave requests go to HR.</p>
    <ul v-else class="team__managers">
      <li v-for="m in record.managers" :key="m.user_id" class="team__person">
        <EmployeeAvatar :user-id="m.user_id" :name="m.name" :avatar-url="null" :size="34" />
        <span class="team__text">
          <component :is="canViewEmployees ? RouterLink : 'span'" v-bind="profileLink(m.user_id)" class="team__name">
            {{ m.name }}
          </component>
          <span class="team__sub">{{ managerNote(m) }}</span>
        </span>
      </li>
    </ul>
    <div v-for="group in groups" :key="group.key" class="team__peers">
      <span class="team__stack" aria-hidden="true">
        <EmployeeAvatar
          v-for="person in group.people.slice(0, MAX_FACES)"
          :key="person.user_id"
          :user-id="person.user_id"
          :name="person.name"
          :avatar-url="person.avatar_url"
          :size="28"
          class="team__face"
        />
      </span>
      <span>{{ group.line }}</span>
    </div>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AppPanel from '@/components/common/AppPanel.vue'
import EmployeeAvatar from '@/components/people/EmployeeAvatar.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useTeamDirectory } from '@/composables/useTeamDirectory'
import type { EmployeeRecord, ManagerRef } from '@/types/employee'
import { reportsOf } from '@/utils/employeeDirectory'

const props = defineProps<{ record: EmployeeRecord }>()
const MAX_FACES = 4

const { canViewEmployees } = usePermissions()
const directory = useTeamDirectory()
const primary = computed(() => props.record.managers.find(m => m.is_primary) ?? null)

function profileLink(userId: string): Record<string, unknown> {
  return canViewEmployees.value ? { to: { name: 'employee-profile', params: { userId } } } : {}
}

function managerNote(m: ManagerRef): string {
  const role = m.is_primary ? 'Primary manager' : 'Manager'
  return m.is_active ? role : `${role} · deactivated`
}

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

// Peers under the same primary manager, then this person's own reports.
const groups = computed(() => {
  const self = props.record.user_id
  const rows = directory.rows.value
  const peers = primary.value ? reportsOf(rows, primary.value.user_id, self) : []
  const reports = reportsOf(rows, self, self)
  return [
    {
      key: 'peers',
      people: peers,
      line: `${count(peers.length, 'other reports', 'others report')} to ${primary.value?.name ?? ''}`,
    },
    {
      key: 'reports',
      people: reports,
      line: `${count(reports.length, 'person reports', 'people report')} to ${props.record.name}`,
    },
  ].filter(group => group.people.length)
})

// The directory is open to employees:view only; without it, managers only.
watch(
  canViewEmployees,
  allowed => {
    if (allowed) void directory.ensureLoaded()
    else directory.clear()
  },
  { immediate: true },
)
</script>

<style scoped>
.team__managers {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.team__person {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.team__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.team__name {
  font-size: 14px;
  font-weight: 500;
  color: inherit;
  text-decoration: none;
}
a.team__name:hover {
  text-decoration: underline;
}
.team__sub,
.team__empty {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.team__empty {
  margin: 0;
  font-size: 14px;
}
.team__peers {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-rule-2);
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
.team__stack {
  display: flex;
  padding-left: 6px;
}
.team__face {
  margin-left: -6px;
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgb(var(--v-theme-surface));
}
</style>
