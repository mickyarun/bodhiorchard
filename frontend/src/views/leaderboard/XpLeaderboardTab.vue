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

<!-- XP standings: every member ranked by XP from real dev work, with a
     bar relative to the leader. -->
<template>
  <LeaderboardBoard
    :entries="entries"
    label="Everyone by XP"
    empty-text="No XP earned yet."
    :loading="loading"
    :error="xpStore.leaderboardError"
    @retry="load"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import LeaderboardBoard from '@/components/leaderboard/LeaderboardBoard.vue'
import { useAuthStore } from '@/stores/auth'
import { useXPStore } from '@/stores/xp'
import { xpBoard } from '@/utils/leaderboard'

const xpStore = useXPStore()
const authStore = useAuthStore()
const loading = ref(true)

const entries = computed(() => xpBoard(xpStore.leaderboard, authStore.user?.id ?? ''))

async function load(): Promise<void> {
  loading.value = true
  await xpStore.fetchLeaderboard()
  loading.value = false
}

onMounted(load)
</script>
