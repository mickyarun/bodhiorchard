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

<!-- The BUD's activity, newest first: the latest few events, and the rest
     on request. The timeline endpoint returns events oldest first. -->
<template>
  <AppPanel title="Activity" :note="events.length ? `${events.length} events` : undefined">
    <template v-if="events.length > RECENT" #action>
      <button type="button" class="activity__toggle" :aria-expanded="showAll" @click="showAll = !showAll">
        {{ showAll ? 'Show recent' : 'Show all' }}
      </button>
    </template>
    <BUDTimeline :events="shown" :loading="loading" />
  </AppPanel>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { TimelineEvent } from '@/types'
import BUDTimeline from './BUDTimeline.vue'

const props = defineProps<{
  events: TimelineEvent[]
  loading: boolean
}>()

const RECENT = 6
const showAll = ref(false)
const shown = computed(() => {
  const newestFirst = [...props.events].reverse()
  return showAll.value ? newestFirst : newestFirst.slice(0, RECENT)
})
</script>

<style scoped>
.activity__toggle {
  border: 0;
  padding: 0;
  background: transparent;
  font: inherit;
  color: var(--color-accent-text);
  cursor: pointer;
}
.activity__toggle:hover {
  text-decoration: underline;
}
</style>
