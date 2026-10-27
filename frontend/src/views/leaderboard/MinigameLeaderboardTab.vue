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

<!-- Best scores for one mini game. Games never award XP; the play count is
     shown to admins only. -->
<template>
  <LeaderboardBoard
    :entries="entries"
    :label="`${gameName} scores`"
    :empty-text="`No scores yet for ${gameName}. Play it in the dashboard's 3D view to take the top spot.`"
    :loading="loading"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import LeaderboardBoard from '@/components/leaderboard/LeaderboardBoard.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useAuthStore } from '@/stores/auth'
import { useMinigamesStore } from '@/stores/minigames'
import type { BoardEntry } from '@/utils/leaderboard'

const props = defineProps<{ game: string; gameName: string }>()

const store = useMinigamesStore()
const authStore = useAuthStore()
const { isOrgAdmin } = usePermissions()
const loading = ref(false)

const entries = computed<BoardEntry[]>(() =>
  (store.leaderboards[props.game] ?? []).map(row => ({
    key: row.user_id,
    name: row.user_name,
    figure: row.best_score.toLocaleString('en-US'),
    note: isOrgAdmin.value ? `${row.plays} ${row.plays === 1 ? 'play' : 'plays'}` : undefined,
    isMe: row.user_id === authStore.user?.id,
  })),
)

async function load(game: string): Promise<void> {
  loading.value = true
  try {
    await store.fetchLeaderboard(game)
  } finally {
    loading.value = false
  }
}

watch(() => props.game, g => void load(g))
onMounted(() => void load(props.game))
</script>
