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

<!-- Top of an approval: who is asking (role, which queue, status), what
     they asked for in three tiles, and their reason when they gave one. -->
<template>
  <div class="head">
    <span class="head__avatar" aria-hidden="true">{{ initialsOf(request.user.name) }}</span>
    <div class="head__who">
      <h2 :id="headingId" class="head__name" tabindex="-1">{{ request.user.name }}</h2>
      <span v-if="role" class="head__role">{{ role }}</span>
    </div>
    <span class="head__route">{{ ROUTE_TAGS[item.route] }}</span>
    <LeaveStatusChip :status="request.status" />
  </div>
  <dl class="tiles">
    <div class="tiles__tile"><dt>Request</dt><dd>{{ requestTypeLabel(request) }}</dd></div>
    <div class="tiles__tile"><dt>Dates</dt><dd>{{ formatDayRange(request.start_date, request.end_date) }}</dd></div>
    <div class="tiles__tile"><dt>Working days</dt><dd>{{ length }}</dd></div>
  </dl>
  <blockquote v-if="request.reason" class="reason">“{{ request.reason }}”</blockquote>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LeaveStatusChip from '@/components/leave/LeaveStatusChip.vue'
import type { ApprovalItem } from '@/types/leave'
import { initialsOf } from '@/utils/avatar'
import { requestLength, requestTypeLabel, ROUTE_TAGS } from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'

const props = defineProps<{ item: ApprovalItem; headingId: string }>()

const request = computed(() => props.item.request)
const role = computed(() => [props.item.designation, props.item.department].filter(Boolean).join(' · '))
const length = computed(() => requestLength(request.value))
</script>

<style scoped>
.head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 14px;
}
.head__avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 16px;
  font-weight: 600;
  background: rgba(var(--v-theme-brand), 0.14);
  color: rgb(var(--v-theme-brand));
}
.head__who {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1 1 160px;
  min-width: 0;
}
.head__name {
  margin: 0;
  outline: none;
  font-size: var(--text-md);
  font-weight: 600;
}
.head__role {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.head__route {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid rgb(var(--v-theme-rule));
  color: rgb(var(--v-theme-ink-2));
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
  margin: 0;
}
.tiles__tile {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tiles__tile dt {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.tiles__tile dd {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.reason {
  margin: 0;
  padding: 14px 16px;
  border-radius: 10px;
  background: rgb(var(--v-theme-surface-variant));
  font-size: var(--text-sm);
  line-height: 20px;
  color: rgb(var(--v-theme-ink-2));
}
</style>
