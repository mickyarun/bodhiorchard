<!-- Copyright 2025-2026 Arun Rajkumar; licensed under Apache-2.0. -->
<template>
  <Transition name="live-matches">
    <aside v-if="matches.length" class="live-matches" aria-label="Live matches">
      <header class="live-matches__header">
        <span><i /> Live matches</span>
        <b>{{ matches.length }}</b>
      </header>
      <div class="live-matches__list">
        <article v-for="match in matches" :key="`${match.kind}-${match.roomId}`" class="live-match">
          <div class="live-match__icon" :class="`live-match__icon--${match.kind}`">
            <v-icon :icon="match.icon" size="18" />
          </div>
          <div class="live-match__copy">
            <span>{{ match.eyebrow }}</span>
            <strong>{{ match.title }}</strong>
            <small>{{ match.detail }}</small>
          </div>
          <button type="button" @click="openMatch(match)">
            {{ match.isParticipant ? 'Rejoin' : 'Watch' }}
            <v-icon icon="mdi-arrow-right" size="14" />
          </button>
        </article>
      </div>
    </aside>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { isBacklashLivePhase } from '@shared/minigames/backlashSocial'
import {
  OrgRoomClient,
  type ActiveBacklashSummary,
  type ActiveRaceSummary,
} from '@/multiplayer/OrgRoomClient'

interface LiveMatch {
  roomId: string
  kind: 'race' | 'backlash'
  icon: string
  eyebrow: string
  title: string
  detail: string
  isParticipant: boolean
}

const router = useRouter()
const auth = useAuthStore()
const races = ref<ActiveRaceSummary[]>([])
const backlashes = ref<ActiveBacklashSummary[]>([])
const unsubscribers: Array<() => void> = []
let connectTimer: number | null = null

const matches = computed<LiveMatch[]>(() => {
  const userId = auth.user?.id ?? ''
  const liveRaces = races.value
    .filter((race) => race.phase === 'countdown' || race.phase === 'running')
    .map((race): LiveMatch => ({
      roomId: race.roomId,
      kind: 'race',
      icon: 'mdi-flag-checkered',
      eyebrow: race.phase === 'countdown' ? 'Starting now' : 'Race in progress',
      title: `${race.hostName}'s ${race.distanceM} m race`,
      detail: `${race.racerCount} racers`,
      isParticipant: Boolean(userId && race.participantUserIds.includes(userId)),
    }))
  const liveBacklashes = backlashes.value
    .filter((match) => isBacklashLivePhase(match.phase))
    .map((match): LiveMatch => ({
      roomId: match.roomId,
      kind: 'backlash',
      icon: 'mdi-circle-double',
      eyebrow: 'Backlash in progress',
      title: `${match.hostName} vs ${match.invitedName}`,
      detail: watcherDetail(match.viewerNames),
      isParticipant: Boolean(userId && match.participantUserIds.includes(userId)),
    }))
  return [...liveBacklashes, ...liveRaces]
})

onMounted(() => {
  const client = OrgRoomClient.getInstance()
  unsubscribers.push(
    client.addActiveRaceListener((next) => { races.value = next }),
    client.addActiveBacklashListener((next) => { backlashes.value = next }),
  )
  connectTimer = window.setTimeout(() => {
    connectTimer = null
    const user = auth.user
    if (
      !user
      || !auth.token
      || (client.connectionStatus !== 'disconnected' && client.connectionStatus !== 'failed')
    ) return
    void client.connect(user.org_id, {
      userId: user.id,
      name: user.name,
      characterModel: user.character_model ?? undefined,
      token: auth.token,
    }).catch((error: unknown) => {
      console.warn('[LiveMatchesPanel] Could not subscribe to live matches:', error)
    })
  }, 0)
})

onBeforeUnmount(() => {
  if (connectTimer !== null) window.clearTimeout(connectTimer)
  for (const unsubscribe of unsubscribers) unsubscribe()
  unsubscribers.length = 0
})

function openMatch(match: LiveMatch): void {
  if (match.kind === 'race') {
    void router.push({ name: 'race-view', params: { roomId: match.roomId } })
    return
  }
  void router.push({ name: 'backlash-room', params: { roomId: match.roomId } })
}

function watcherDetail(viewerNames: readonly string[]): string {
  if (viewerNames.length === 0) return 'No viewers yet'
  if (viewerNames.length === 1) return `${viewerNames[0]} is watching`
  const visibleNames = viewerNames.slice(0, 2).join(', ')
  const remaining = viewerNames.length - 2
  return remaining > 0
    ? `${visibleNames} +${remaining} watching`
    : `${visibleNames} watching`
}
</script>

<style scoped>
.live-matches {
  position: absolute;
  z-index: 14;
  top: 16px;
  right: 16px;
  width: min(390px, calc(100% - 32px));
  overflow: hidden;
  border: 1px solid rgba(191, 137, 77, .28);
  border-radius: 16px;
  background: rgba(18, 15, 12, .91);
  color: #fff4df;
  box-shadow: 0 18px 48px rgba(0, 0, 0, .34);
  backdrop-filter: blur(16px);
}
.live-matches__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 9px;
  border-bottom: 1px solid rgba(255, 255, 255, .08);
  color: #e8bc85;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.live-matches__header span { display: inline-flex; align-items: center; gap: 8px; }
.live-matches__header i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #65dd7b;
  box-shadow: 0 0 0 5px rgba(101, 221, 123, .12);
  animation: live-dot 1.5s infinite;
}
.live-matches__header b {
  display: grid;
  place-items: center;
  min-width: 22px;
  height: 22px;
  border-radius: 999px;
  background: rgba(255, 255, 255, .08);
}
.live-matches__list { max-height: 270px; overflow-y: auto; padding: 6px; }
.live-match { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 10px; border-radius: 11px; }
.live-match + .live-match { border-top: 1px solid rgba(255, 255, 255, .06); }
.live-match__icon { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; }
.live-match__icon--backlash { background: linear-gradient(145deg, #773624, #311915); color: #ffc28b; }
.live-match__icon--race { background: linear-gradient(145deg, #1f477e, #14233c); color: #9fc9ff; }
.live-match__copy { display: flex; flex-direction: column; min-width: 0; }
.live-match__copy span { color: rgba(255, 244, 223, .45); font-size: 8px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.live-match__copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.live-match__copy small { color: rgba(255, 244, 223, .5); font-size: 9px; }
.live-match button { display: inline-flex; align-items: center; gap: 4px; border: 1px solid rgba(224, 154, 86, .34); border-radius: 999px; padding: 6px 9px; background: rgba(183, 83, 43, .18); color: #ffd1a2; font-size: 10px; font-weight: 800; cursor: pointer; }
.live-match button:hover { background: rgba(183, 83, 43, .34); }
@keyframes live-dot { 60% { box-shadow: 0 0 0 9px transparent; } }
.live-matches-enter-active, .live-matches-leave-active { transition: opacity .2s, transform .2s; }
.live-matches-enter-from, .live-matches-leave-to { opacity: 0; transform: translateY(-8px); }
@media (max-width: 600px) {
  .live-matches { top: 10px; right: 10px; width: calc(100% - 20px); }
}
@media (prefers-reduced-motion: reduce) {
  .live-matches__header i { animation: none; }
}
</style>
