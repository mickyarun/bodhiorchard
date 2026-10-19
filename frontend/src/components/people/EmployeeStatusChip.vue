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

<!-- Employee status badge. Active shows nothing unless asked: the
     directory only flags people who are on notice or have left. -->
<template>
  <v-chip
    v-if="status !== 'active' || showActive"
    size="small"
    variant="tonal"
    label
    :color="COLORS[status]"
    :prepend-icon="ICONS[status]"
  >
    {{ STATUS_LABELS[status] }}
  </v-chip>
</template>

<script setup lang="ts">
import type { EmployeeStatus } from '@/types/employee'
import { STATUS_LABELS } from '@/utils/employee'

withDefaults(defineProps<{ status: EmployeeStatus; showActive?: boolean }>(), {
  showActive: false,
})

const COLORS: Record<EmployeeStatus, string> = {
  active: 'success',
  on_notice: 'warning',
  exited: 'default',
}
const ICONS: Record<EmployeeStatus, string> = {
  active: 'mdi-check',
  on_notice: 'mdi-timer-sand',
  exited: 'mdi-logout',
}
</script>
