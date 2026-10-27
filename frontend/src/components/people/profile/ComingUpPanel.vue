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

<!-- "Coming up" beside the profile: the next work anniversary and, when the
     viewer can see the date of birth, the next birthday (never the year). -->
<template>
  <AppPanel v-if="anniversary || birthday" title="Coming up">
    <ul class="coming">
      <li v-if="anniversary">
        {{ anniversary.years }}-year work anniversary on <strong>{{ formatFullDate(anniversary.date) }}</strong>.
        <span v-if="personal && !personal.celebrate_anniversary" class="coming__muted">Not announced.</span>
      </li>
      <li v-if="birthday">
        Birthday on <strong>{{ formatDayMonth(birthday) }}</strong>.
        <span v-if="personal && !personal.celebrate_birthday" class="coming__muted">Not announced.</span>
      </li>
    </ul>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { EmployeeRecord } from '@/types/employee'
import { formatDayMonth, formatFullDate, nextAnniversary, nextBirthday } from '@/utils/employeeProfile'

const props = defineProps<{ record: EmployeeRecord }>()

const today = new Date()
const personal = computed(() => props.record.personal)
// Nothing is coming up for someone who has left.
const exited = computed(() => props.record.work.status === 'exited')
const anniversary = computed(() =>
  exited.value ? null : nextAnniversary(props.record.work.date_of_joining, today),
)
const birthday = computed(() =>
  exited.value ? null : nextBirthday(personal.value?.date_of_birth ?? null, today),
)
</script>

<style scoped>
.coming {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-ink-2));
}
.coming strong {
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}
.coming__muted {
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
