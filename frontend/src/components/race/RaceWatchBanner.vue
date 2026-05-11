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
  <transition name="slide-down">
    <div v-if="featured" class="race-watch-banner">
      <span class="race-watch-banner__text">
        {{ featured.hostName }} is racing {{ featured.distanceM }} m
      </span>
      <v-btn
        size="small"
        variant="flat"
        color="primary"
        @click="watch"
      >
        Watch
      </v-btn>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { OrgRoomClient, type ActiveRaceSummary } from '@/multiplayer/OrgRoomClient'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const summaries = ref<ActiveRaceSummary[]>([])
const unsubscribe = ref<(() => void) | null>(null)

/**
 * Featured race = first entry that is neither
 *   (a) the race the user is currently viewing, nor
 *   (b) a race the user is a participant of (host / invitee).
 * Case (b) handles the scenario where a racer temporarily navigates back
 * to /dashboard mid-race — a "Watch" button pointing at their own race
 * is confusing. They can rejoin from the notification bell instead.
 */
const featured = computed<ActiveRaceSummary | null>(() => {
  const currentRoomId = route.name === 'race-view' ? String(route.params.roomId ?? '') : ''
  const selfId = authStore.user?.id ?? ''
  return (
    summaries.value.find(
      s =>
        s.roomId !== currentRoomId &&
        s.phase !== 'finished' &&
        !(selfId && s.participantUserIds.includes(selfId)),
    ) ?? null
  )
})

onMounted(() => {
  const client = OrgRoomClient.getInstance()
  // The OrgRoomClient may not be connected yet (user not on the garden
  // page). The listener fires with an empty list until the room is joined;
  // that's fine — banner stays hidden via `featured` being null.
  unsubscribe.value = client.addActiveRaceListener((next) => {
    summaries.value = next
  })
})

onBeforeUnmount(() => {
  unsubscribe.value?.()
  unsubscribe.value = null
})

function watch(): void {
  if (!featured.value) return
  router.push(`/raceview/${featured.value.roomId}`)
}
</script>

<style scoped>
.race-watch-banner {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1500;
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(30, 60, 120, 0.9);
  color: #fff;
  padding: 10px 16px;
  border-radius: 20px;
  font-size: 14px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
}
.race-watch-banner__text {
  font-weight: 500;
}

.slide-down-enter-active,
.slide-down-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}
.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translate(-50%, -8px);
}
</style>
