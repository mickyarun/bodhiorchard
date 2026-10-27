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

<!-- One labelled skill bar: the name on the left, the level word on the
     right and a thin neutral meter underneath. The level reads as text;
     the bar is not coloured, since colour is kept for status. -->
<template>
  <div class="skill-meter">
    <div class="skill-meter__row">
      <span class="skill-meter__name">{{ name }}</span>
      <span class="skill-meter__level">{{ skillLevel(score) }}</span>
    </div>
    <div
      class="skill-meter__track"
      role="meter"
      :aria-label="name"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="percent"
      :aria-valuetext="`${skillLevel(score)}, ${percent}%`"
    >
      <span class="skill-meter__fill" :style="{ width: `${percent}%` }" />
    </div>
    <span v-if="detail" class="skill-meter__detail">{{ detail }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { scorePercent, skillLevel } from '@/utils/skillProfiles'

const props = defineProps<{ name: string; score: number; detail?: string }>()

const percent = computed(() => scorePercent(props.score))
</script>

<style scoped>
.skill-meter {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.skill-meter__row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.skill-meter__name {
  min-width: 0;
  overflow-wrap: anywhere;
  color: rgb(var(--v-theme-ink-2));
}
.skill-meter__level {
  flex-shrink: 0;
  color: rgb(var(--v-theme-on-surface-variant));
}
.skill-meter__track {
  height: 6px;
  border-radius: 999px;
  background: rgb(var(--v-theme-surface-variant));
  overflow: hidden;
}
.skill-meter__fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: rgb(var(--v-theme-on-surface-variant));
}
.skill-meter__detail {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
