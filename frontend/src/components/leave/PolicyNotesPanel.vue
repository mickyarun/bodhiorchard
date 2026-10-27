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

<!-- My leave sidebar: how the caller's policy handles requests, in plain
     sentences built from the policy itself. -->
<template>
  <AppPanel title="Good to know">
    <ul class="notes">
      <li v-for="note in notes" :key="note">{{ note }}</li>
    </ul>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { LeaveSummary } from '@/types/leave'
import { policyNotes } from '@/utils/leaveHome'

const props = defineProps<{ summary: LeaveSummary }>()
const notes = computed(() => policyNotes(props.summary))
</script>

<style scoped>
.notes {
  margin: 0;
  padding: 0 0 0 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: var(--text-sm);
  line-height: 20px;
  color: rgb(var(--v-theme-ink-2));
}
</style>
