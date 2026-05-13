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

<script setup lang="ts">
import { ref } from 'vue'
import type { TimelineEvent } from '@/types'
import BUDTimeline from './BUDTimeline.vue'

defineProps<{
  events: TimelineEvent[]
  loading: boolean
}>()

const open = ref(false)
</script>

<template>
  <div class="timeline-section mt-4">
    <button class="timeline-toggle" @click="open = !open">
      <v-icon :icon="open ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="18" />
      <span class="text-subtitle-2 font-weight-medium">Activity</span>
      <span class="text-caption text-medium-emphasis ml-1">({{ events.length }})</span>
    </button>
    <div v-if="open" class="timeline-body">
      <BUDTimeline :events="events" :loading="loading" />
    </div>
  </div>
</template>

<style scoped>
.timeline-section {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
}

.timeline-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 10px 14px;
  background: none;
  border: none;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.87);
  text-align: left;
}

.timeline-toggle:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 8px;
}

.timeline-body {
  padding: 0 14px 14px;
}
</style>
