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

<!-- One lifecycle stage on the board: a stage-coloured dot, the name and
     count, then its cards. -->
<template>
  <section class="board-column" :aria-label="`${label}, ${buds.length === 1 ? '1 BUD' : `${buds.length} BUDs`}`">
    <header class="board-column__head">
      <span class="board-column__dot" :style="{ background: `rgb(var(--v-theme-${BUD_STATUS_COLORS[status]}))` }" />
      <h2 class="board-column__name">{{ label }}</h2>
      <span class="board-column__count">{{ buds.length }}</span>
    </header>
    <BoardCard
      v-for="bud in buds"
      :key="bud.id"
      :bud="bud"
      :now="now"
      :can-restore="canRestore"
      @restore="emit('restore', $event)"
    />
    <p v-if="!buds.length" class="board-column__empty">{{ filtering ? 'No matches' : 'Nothing here' }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BoardCard from './BoardCard.vue'
import { BUD_STATUS_COLORS, BUD_STATUS_LABELS, type BUDListItem, type BUDStatus } from '@/types'

const props = defineProps<{
  status: BUDStatus
  buds: BUDListItem[]
  now: Date
  filtering: boolean
  canRestore: boolean
}>()

const emit = defineEmits<{ restore: [bud: BUDListItem] }>()

const label = computed(() => BUD_STATUS_LABELS[props.status])
</script>

<style scoped>
.board-column {
  width: 272px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgb(var(--v-theme-rule));
  background: rgba(var(--v-theme-on-surface), 0.03);
}
.board-column__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 4px 2px;
}
.board-column__dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  flex-shrink: 0;
}
.board-column__name {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}
.board-column__count {
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface-variant));
}
.board-column__empty {
  margin: 0;
  padding: 16px 4px;
  text-align: center;
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
