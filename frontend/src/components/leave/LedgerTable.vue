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

<!-- Allocations and adjustments behind a member's balances. -->
<template>
  <p v-if="!entries.length" class="text-body-2 text-medium-emphasis">
    No allocations or adjustments this leave year.
  </p>
  <v-table v-else density="comfortable">
    <thead>
      <tr>
        <th>Date</th>
        <th>Type</th>
        <th>Days</th>
        <th>Note</th>
        <th>By</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="entry in entries" :key="entry.id">
        <td>{{ formatDateOnly(entry.created_at) }}</td>
        <td>{{ typeNames[entry.leave_type_id] ?? '—' }}</td>
        <td :class="toNumber(entry.days) < 0 ? 'text-error' : 'text-success'">
          {{ formatSignedDays(toNumber(entry.days)) }}
        </td>
        <td>{{ entry.note || (entry.entry_type === 'allocation' ? 'Yearly allocation' : '—') }}</td>
        <td>{{ entry.created_by?.name ?? 'Automatic' }}</td>
      </tr>
    </tbody>
  </v-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Balance } from '@/types/leave'
import type { LedgerEntryRead } from '@/types/leavePolicy'
import { formatDateOnly } from '@/utils/employee'
import { formatSignedDays, toNumber } from '@/utils/leave'

const props = defineProps<{ entries: LedgerEntryRead[]; balances: Balance[] }>()

const typeNames = computed<Record<string, string>>(() =>
  Object.fromEntries(props.balances.map(b => [b.leave_type.id, b.leave_type.name])),
)
</script>
