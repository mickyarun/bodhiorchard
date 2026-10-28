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

<!-- One BUD on the board. The title link stretches over the whole card,
     so the bug-count link and the Restore button sit above it and stay
     separately clickable without nesting interactive elements. -->
<template>
  <article class="board-card">
    <div class="board-card__top">
      <span class="board-card__ref">{{ budRef(bud.bud_number) }}</span>
      <BudPriorityChip :priority="bud.priority" />
      <span
        v-if="bud.complexity"
        class="board-card__dots"
        role="img"
        :aria-label="`Complexity ${bud.complexity} of 5`"
      >
        <span v-for="i in 5" :key="i" class="board-card__dot" :class="{ 'board-card__dot--on': i <= bud.complexity }" />
      </span>
    </div>

    <h3 class="board-card__title">
      <router-link :to="`/buds/${bud.id}`" class="board-card__link">{{ bud.title }}</router-link>
    </h3>

    <span v-for="line in lines" :key="line.text" class="board-card__status" :class="`board-card__status--${line.tone}`">
      <span class="board-card__status-dot" aria-hidden="true" />{{ line.text }}
    </span>

    <div class="board-card__foot">
      <span class="board-card__age" :title="`Opened ${formatDate(bud.created_at)}, updated ${formatDate(bud.updated_at)}`">
        {{ budAge(bud.created_at, now) }}
      </span>
      <router-link
        v-if="bud.open_bug_count > 0"
        :to="`/bugs?budId=${bud.id}`"
        class="board-card__bugs"
        :aria-label="bud.open_bug_count === 1 ? '1 open bug' : `${bud.open_bug_count} open bugs`"
      >
        <v-icon icon="mdi-bug-outline" size="14" />{{ bud.open_bug_count }}
      </router-link>
      <v-btn
        v-if="bud.status === 'discarded' && canRestore"
        variant="text"
        size="x-small"
        color="primary"
        prepend-icon="mdi-restore"
        class="board-card__restore"
        @click="emit('restore', bud)"
      >
        Restore
      </v-btn>
      <AppMonogram
        v-if="bud.assignee_name"
        class="board-card__avatar"
        :name="bud.assignee_name"
        :size="24"
        :title="bud.assignee_name"
        :label="`Assigned to ${bud.assignee_name}`"
      />
      <span
        v-else
        class="board-card__avatar board-card__avatar--empty"
        title="Unassigned"
        role="img"
        aria-label="Unassigned"
      />
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BudPriorityChip from '@/components/buds/BudPriorityChip.vue'
import AppMonogram from '@/components/common/AppMonogram.vue'
import { budRef, type BUDListItem } from '@/types'
import { budAge, cardStatusLines } from '@/utils/budBoard'
import { formatDate } from '@/utils/date'

const props = defineProps<{
  bud: BUDListItem
  now: Date
  canRestore: boolean
}>()

const emit = defineEmits<{ restore: [bud: BUDListItem] }>()

const lines = computed(() => cardStatusLines(props.bud, props.now))
</script>

<style scoped>
.board-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 12px 10px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: var(--radius-card);
  transition: border-color var(--dur-short) var(--ease-out);
}
.board-card:hover,
.board-card:focus-within {
  border-color: rgba(var(--v-theme-primary), 0.55);
}
.board-card__top,
.board-card__foot {
  display: flex;
  align-items: center;
  gap: 6px;
}
.board-card__ref {
  font: 500 12px var(--font-mono);
  color: rgb(var(--v-theme-on-surface-variant));
}
.board-card__dots {
  display: inline-flex;
  gap: 3px;
  margin-left: auto;
}
.board-card__dot {
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: rgb(var(--v-theme-rule));
}
.board-card__dot--on {
  background: rgb(var(--v-theme-primary));
}
.board-card__title {
  margin: 0;
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.board-card__link {
  color: inherit;
  text-decoration: none;
}
.board-card__link::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
}
.board-card__link:focus-visible {
  outline: none;
}
.board-card__link:focus-visible::after {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
.board-card__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.board-card__status-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}
.board-card__status--error { color: rgb(var(--v-theme-error)); }
.board-card__status--warning { color: rgb(var(--v-theme-warning)); }
.board-card__status--success { color: rgb(var(--v-theme-success)); }
.board-card__age {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.board-card__bugs,
.board-card__restore {
  position: relative;
  z-index: 1;
}
.board-card__bugs {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 500;
  text-decoration: none;
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.1);
}
.board-card__avatar {
  margin-left: auto;
}
.board-card__avatar--empty {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border-radius: 999px;
  border: 1px dashed rgb(var(--v-theme-on-surface-variant));
}
</style>
