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

<template>
  <div class="race-room-view">
    <div v-if="error" class="pa-6">
      <v-alert type="error" prominent>{{ error }}</v-alert>
      <v-btn class="mt-4" @click="goHome">Back to garden</v-btn>
    </div>

    <template v-else-if="snapshot">
      <RaceLobbyPanel
        v-if="snapshot.phase === 'lobby'"
        :snapshot="snapshot"
        :is-host="isHost"
        @start="onStart"
        @leave="goHome"
      />
      <RaceLivePanel
        v-else-if="snapshot.phase === 'countdown' || snapshot.phase === 'running'"
        :snapshot="snapshot"
        :client="client!"
        :is-participant="isParticipant"
      />
      <RaceResultsCard
        v-else-if="snapshot.phase === 'finished'"
        :snapshot="snapshot"
        @leave="goHome"
      />
    </template>

    <div v-else class="pa-6 d-flex align-center justify-center" style="min-height: 200px;">
      <v-progress-circular indeterminate />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { RaceRoomClient, type RaceStateSnapshot } from '@/multiplayer/RaceRoomClient'
import RaceLobbyPanel from './RaceLobbyPanel.vue'
import RaceLivePanel from './RaceLivePanel.vue'
import RaceResultsCard from './RaceResultsCard.vue'

const props = defineProps<{
  roomId: string
}>()

const router = useRouter()
const authStore = useAuthStore()

const client = ref<RaceRoomClient | null>(null)
const snapshot = ref<RaceStateSnapshot | null>(null)
const error = ref<string>('')

const userId = computed(() => authStore.user?.id ?? '')

const isHost = computed(
  () => !!snapshot.value && snapshot.value.hostUserId === userId.value,
)

const isParticipant = computed(() => {
  if (!snapshot.value) return false
  return snapshot.value.racers.some(r => r.userId === userId.value)
})

watch(
  () => props.roomId,
  (roomId) => { void connect(roomId) },
  { immediate: true },
)

// Auth can still be loading when the user lands directly on /raceview
// (e.g. deep-linked from an invite email). Retry connect() once the user
// resolves, rather than flashing "You must be signed in" at mount time.
watch(
  () => authStore.user,
  (user) => {
    if (user && !snapshot.value && !error.value) void connect(props.roomId)
  },
)

onBeforeUnmount(() => {
  client.value?.destroy()
  client.value = null
})

async function connect(roomId: string): Promise<void> {
  if (!authStore.user) {
    if (!authStore.isAuthenticated) {
      error.value = 'You must be signed in to view a race.'
    }
    return
  }
  const fresh = new RaceRoomClient()
  fresh.onStateChange = (s) => { snapshot.value = s }
  try {
    await fresh.joinById(roomId, {
      userId: authStore.user.id,
      name: authStore.user.name,
      characterModel: authStore.user.character_model ?? '',
      token: authStore.token ?? '',
    })
    client.value = fresh
  } catch (err) {
    console.error('[RaceRoomView] join failed:', err)
    error.value = 'Could not join this race room. It may have ended or the invitation may be invalid.'
    fresh.destroy()
  }
}

function onStart(): void {
  client.value?.sendRaceStart()
}

function goHome(): void {
  // The garden lives at /dashboard. /methodology is the unauthenticated
  // landing page — sending users there from race log them out of context.
  router.push('/dashboard')
}
</script>

<style scoped>
.race-room-view {
  width: 100%;
  height: 100%;
  min-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
}
.race-room-view > * {
  flex: 1;
}
</style>
