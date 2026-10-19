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

<!-- Top of an employee profile: who they are, their role, and where
     they sit (code, managers, joining date, office or remote). -->
<template>
  <v-card color="surface" class="pa-6 mb-4" rounded="lg">
    <div class="d-flex ga-4 align-start flex-wrap">
      <v-avatar size="64" color="primary" variant="tonal">
        <span class="text-h6 font-weight-bold">{{ initials }}</span>
      </v-avatar>
      <div class="flex-grow-1" style="min-width: 0">
        <div class="d-flex align-center ga-2 flex-wrap">
          <h1 class="text-h5 font-weight-bold bo-display">{{ record.name }}</h1>
          <EmployeeStatusChip :status="record.work.status" show-active />
          <v-chip size="x-small" variant="tonal" label>
            {{ EMPLOYMENT_TYPE_LABELS[record.work.employment_type] }}
          </v-chip>
          <v-chip v-if="!record.is_active" size="x-small" variant="tonal" label color="error">
            Account deactivated
          </v-chip>
        </div>
        <div class="text-body-1 text-medium-emphasis">{{ roleLine }}</div>
        <div class="text-caption text-medium-emphasis mt-1">{{ metaLine }}</div>
      </div>
      <slot name="actions" />
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import EmployeeStatusChip from '@/components/people/EmployeeStatusChip.vue'
import type { EmployeeRecord } from '@/types/employee'
import { EMPLOYMENT_TYPE_LABELS, formatDateOnly, workplaceLabel } from '@/utils/employee'

const props = defineProps<{ record: EmployeeRecord }>()

const initials = computed(
  () =>
    props.record.name
      .split(' ')
      .map(part => part[0])
      .join('')
      .toUpperCase()
      .slice(0, 2) || '?',
)

const roleLine = computed(() =>
  [props.record.work.designation, props.record.work.department].filter(Boolean).join(' · ') ||
  props.record.email,
)

const metaLine = computed(() => {
  const { work, managers } = props.record
  const primary = managers.find(m => m.is_primary)
  const extra = managers.length > 1 ? ` +${managers.length - 1}` : ''
  return [
    work.employee_code,
    primary ? `Reports to ${primary.name}${extra}` : 'No manager set',
    work.date_of_joining ? `Joined ${formatDateOnly(work.date_of_joining)}` : null,
    workplaceLabel(work.work_arrangement, props.record.office),
  ]
    .filter(Boolean)
    .join(' · ')
})
</script>
