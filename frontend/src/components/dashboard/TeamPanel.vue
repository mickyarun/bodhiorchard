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

<!-- Team: who is online, on a break or away, plus the daily quiz and games.
     Games never award XP; the streak shown is the player's own. -->
<template>
  <AppPanel title="Team">
    <dl class="team__counts">
      <div v-for="row in counts" :key="row.label" class="team__count">
        <dt>{{ row.label }}</dt>
        <dd>{{ row.value }}</dd>
      </div>
    </dl>
    <div class="team__actions">
      <v-btn variant="outlined" class="flex-grow-1" @click="emit('quiz')">
        Today's quiz
        <span v-if="quizPlayable" class="team__badge">New</span>
      </v-btn>
      <v-btn variant="outlined" class="flex-grow-1" @click="emit('games')">
        Games
        <span v-if="streak > 0" class="team__badge">{{ streak }}-day streak</span>
      </v-btn>
    </div>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { MemberActivity } from '@/types/dashboard'

const props = defineProps<{
  members: MemberActivity[]
  quizPlayable: boolean
  streak: number
}>()

const emit = defineEmits<{ quiz: []; games: [] }>()

const counts = computed(() => {
  const by = (p: MemberActivity['presence']) => props.members.filter(m => m.presence === p).length
  return [
    { label: 'Online', value: by('active') },
    { label: 'On a break', value: by('on_break') },
    { label: 'Away', value: by('at_home') },
  ]
})
</script>

<style scoped>
.team__counts {
  display: flex;
  gap: 24px;
  margin: 0;
}
.team__count {
  display: flex;
  flex-direction: column-reverse;
}
.team__count dt {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.team__count dd {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.team__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
.team__badge {
  margin-left: 6px;
  font-size: 12px;
  font-weight: 400;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
