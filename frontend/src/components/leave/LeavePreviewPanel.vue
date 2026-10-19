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

<!-- What a request would cost and who decides it, from the server's
     preview. Problems explain why it can't be sent yet. -->
<template>
  <div class="preview" aria-live="polite">
    <div v-if="previewing" class="d-flex align-center ga-2 text-body-2 text-medium-emphasis">
      <v-progress-circular indeterminate size="14" width="2" />
      Checking dates…
    </div>
    <AppCallout v-else-if="error" variant="error">{{ error }}</AppCallout>
    <template v-else-if="preview">
      <div class="text-body-2 font-weight-medium">
        {{ daysLine }}<span v-if="skips" class="text-medium-emphasis font-weight-regular"> · {{ skips }}</span>
      </div>
      <div v-if="balanceLine" class="text-body-2 mt-1">{{ balanceLine }}</div>
      <AppCallout v-if="lopLine" variant="warning" class="mt-2">{{ lopLine }}</AppCallout>
      <div v-if="approval" class="text-body-2 text-medium-emphasis mt-1">{{ approval }}</div>
      <AppCallout v-if="preview.problems.length" variant="error" class="mt-3">
        <div v-for="problem in preview.problems" :key="problem.code">{{ problem.message }}</div>
      </AppCallout>
    </template>
    <div v-else class="text-body-2 text-medium-emphasis">{{ placeholder }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import type { LeaveKind, LeavePreview, PolicyBrief } from '@/types/leave'
import {
  approvalLine,
  excludedSummary,
  formatDays,
  lopLabel,
  toNumber,
  toNumberOrNull,
} from '@/utils/leave'

const props = defineProps<{
  preview: LeavePreview | null
  previewing: boolean
  error: string
  kind: LeaveKind
  policy: PolicyBrief | null
  /** Leave type name for the balance line. */
  typeName: string
  placeholder: string
}>()

const daysLine = computed(() => {
  const days = toNumber(props.preview?.days)
  return `${formatDays(days)} working ${days === 1 ? 'day' : 'days'}`
})

const skips = computed(() =>
  props.preview ? excludedSummary(props.preview.excluded, props.policy?.working_days ?? []) : '',
)

// Days past the balance aren't refused: they're unpaid.
const lopLine = computed(() => {
  const lop = lopLabel(props.preview?.lop_days)
  return lop ? `${lop}: these days are past your ${props.typeName ?? 'leave'} balance, so they're unpaid.` : ''
})

const balanceLine = computed(() => {
  if (props.kind !== 'leave' || !props.preview) return ''
  const before = toNumberOrNull(props.preview.balance_before)
  const after = toNumberOrNull(props.preview.balance_after)
  if (before === null || after === null) return ''
  return `${props.typeName} ${formatDays(before)} → ${formatDays(after)} ${after === 1 ? 'day' : 'days'} left`
})

const approval = computed(() =>
  props.preview ? approvalLine(props.preview, props.kind, props.policy?.wfh_approval ?? null) : '',
)
</script>

<style scoped>
.preview {
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  min-height: 48px;
}
</style>
