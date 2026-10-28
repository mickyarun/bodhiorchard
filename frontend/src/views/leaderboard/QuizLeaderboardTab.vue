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

<!-- This month's quiz standings. No XP for the quiz: the month's top scorer
     earns SP instead. A board where nobody has scored stays empty. -->
<template>
  <div class="quiz-board">
    <p class="quiz-board__note">The top scorer this month earns SP. The quiz never awards XP.</p>
    <LeaderboardBoard
      :entries="entries"
      label="Quiz points this month"
      empty-text="No points on the board yet this month."
      :loading="store.monthlyLoading"
      :error="store.monthlyError"
      @retry="store.fetchMonthly()"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import LeaderboardBoard from '@/components/leaderboard/LeaderboardBoard.vue'
import { useAuthStore } from '@/stores/auth'
import { useQuizStore } from '@/stores/quiz'
import type { BoardEntry } from '@/utils/leaderboard'

const store = useQuizStore()
const authStore = useAuthStore()

// Someone has to score to lead: a board of zeros shows as empty.
const entries = computed<BoardEntry[]>(() =>
  (store.monthly[0]?.totalPoints ?? 0) > 0
    ? store.monthly.map(e => ({
        key: e.userId,
        name: e.userName,
        avatarUrl: e.avatarUrl,
        figure: e.totalPoints.toLocaleString('en-US'),
        unit: 'pts',
        note: `${e.correctCount} correct`,
        isMe: e.userId === authStore.user?.id,
      }))
    : [],
)

onMounted(() => store.fetchMonthly())
</script>

<style scoped>
.quiz-board {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.quiz-board__note {
  margin: 0;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
