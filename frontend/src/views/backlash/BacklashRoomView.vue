<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->
<template>
  <main class="backlash-shell">
    <div class="ambient ambient--one" />
    <div class="ambient ambient--two" />

    <header class="topbar">
      <button class="back-button" type="button" @click="leaveGame">
        <v-icon icon="mdi-arrow-left" size="18" /> Garden Games
      </button>
      <div class="brand">
        <span>BACKLASH</span>
        <small>A tactical game of take or be taken</small>
      </div>
      <button class="rules-button" type="button" @click="rulesOpen = !rulesOpen">
        <v-icon icon="mdi-book-open-variant" size="17" /> Rules
      </button>
    </header>

    <div v-if="connectionStatus !== 'connected'" class="connection-banner" role="status">
      <v-progress-circular v-if="connectionStatus === 'reconnecting'" indeterminate size="16" width="2" />
      {{ connectionStatus === 'reconnecting' ? 'Connection lost — rejoining your match…' : 'Disconnected from the match.' }}
    </div>

    <v-alert v-if="error" type="error" closable class="error-alert" @click:close="error = ''">
      {{ error }}
    </v-alert>

    <section v-if="loading" class="loading-panel">
      <div class="loading-piece" />
      <h2>Setting the board</h2>
      <p>Joining the private match room…</p>
    </section>

    <section v-else-if="state" class="game-layout">
      <aside class="player-card" :class="playerCardClass(topPlayer)">
        <div class="player-card__token" :class="pieceColorClass(topPlayer?.color)">
          {{ initials(topPlayer?.name) }}
        </div>
        <div class="player-card__copy">
          <span class="player-card__label">{{ isViewer ? topColorLabel : 'Opponent' }}</span>
          <strong>{{ topPlayer?.name || 'Waiting for opponent…' }}</strong>
          <span class="player-card__status">
            <i :class="{ offline: topPlayer && !topPlayer.connected }" />
            {{ topPlayer ? (topPlayer.connected ? 'Connected' : 'Reconnecting') : 'Invited' }}
          </span>
        </div>
        <div v-if="topPlayer" class="player-card__score">
          <strong>{{ pieceTotal(topPlayer.color) }}</strong><span>pieces</span>
        </div>
      </aside>

      <section class="table-area">
        <div class="turn-strip" :class="{ 'turn-strip--mine': isMyTurn }">
          <span class="turn-strip__content">
            <template v-if="state.phase === 'lobby'">
              <v-progress-circular indeterminate size="16" width="2" /> Waiting for your opponent to accept
            </template>
            <template v-else-if="state.phase === 'finished'">Match complete</template>
            <template v-else-if="isMyTurn">
              <span class="turn-pulse" /> Your turn
              <span class="turn-strip__hint">{{ turnHint }}</span>
            </template>
            <template v-else>
              {{ turnPlayer?.name || 'Opponent' }} is thinking
            </template>
          </span>
          <span v-if="turnSeconds !== null" class="turn-clock" :class="{ urgent: turnSeconds <= 10 }">
            {{ turnSeconds }}s
          </span>
        </div>

        <div class="capture-rack capture-rack--opponent">
          <span class="capture-rack__label">Removed from {{ topPlayer?.name || 'opponent' }}</span>
          <TransitionGroup name="captured-token" tag="div" class="capture-rack__pieces">
            <span
              v-for="piece in removedTopPieces"
              :key="piece.id"
              class="capture-token"
              :class="[`capture-token--${piece.color}`, `capture-token--${piece.kind}`]"
              :title="`${capitalize(piece.color)} ${piece.kind}`"
            >
              <b v-if="piece.kind === 'overling'">B</b>
            </span>
          </TransitionGroup>
          <span v-if="removedTopPieces.length === 0" class="capture-rack__empty">None</span>
        </div>

        <div class="board-frame" :class="{ 'board-frame--locked': !canInteract }">
          <div class="wood-grain" aria-hidden="true" />
          <div class="board" role="grid" aria-label="Backlash board">
            <button
              v-for="index in displayIndices"
              :key="index"
              class="square"
              :class="squareClasses(index)"
              type="button"
              role="gridcell"
              :aria-label="squareLabel(index)"
              :disabled="!canInteract"
              @click="selectSquare(index)"
            >
              <span v-if="legalTargetSet.has(index)" class="legal-dot" />
            </button>

            <div
              v-for="item in positionedPieces"
              :key="item.piece.id"
              class="piece"
              :class="[
                `piece--${item.piece.color}`,
                `piece--${item.piece.kind}`,
                { 'piece--selected': selectedIndex === item.index },
              ]"
              :style="item.style"
              aria-hidden="true"
            >
              <span class="piece__rim" />
              <span v-if="item.piece.kind === 'overling'" class="piece__crown">B</span>
            </div>

            <div
              v-for="effect in positionedCaptureEffects"
              :key="effect.key"
              class="capture-effect"
              :style="effect.style"
              aria-hidden="true"
            >
              <span class="capture-effect__burst" />
              <span
                class="capture-effect__coin"
                :class="[
                  `capture-effect__coin--${effect.piece.color}`,
                  `capture-effect__coin--${effect.piece.kind}`,
                ]"
              >
                <b v-if="effect.piece.kind === 'overling'">B</b>
              </span>
            </div>
          </div>
          <div class="board-mark board-mark--top">{{ topColorLabel }}</div>
          <div class="board-mark board-mark--bottom">{{ bottomColorLabel }}</div>
          <TransitionGroup name="crowd-reaction">
            <div
              v-for="reaction in encouragementVisuals"
              :key="reaction.key"
              class="crowd-reaction"
              :class="`crowd-reaction--${reaction.slot}`"
              aria-live="polite"
            >
              <strong>{{ reaction.reaction }}</strong>
              <span>{{ reaction.name }}</span>
            </div>
          </TransitionGroup>
        </div>

        <div class="capture-rack capture-rack--mine">
          <span class="capture-rack__label">Removed from {{ bottomPlayer?.name || 'player' }}</span>
          <TransitionGroup name="captured-token" tag="div" class="capture-rack__pieces">
            <span
              v-for="piece in removedBottomPieces"
              :key="piece.id"
              class="capture-token"
              :class="[`capture-token--${piece.color}`, `capture-token--${piece.kind}`]"
              :title="`${capitalize(piece.color)} ${piece.kind}`"
            >
              <b v-if="piece.kind === 'overling'">B</b>
            </span>
          </TransitionGroup>
          <span v-if="removedBottomPieces.length === 0" class="capture-rack__empty">None</span>
        </div>

        <div v-if="state.phase === 'jump' && isMyTurn" class="chain-panel">
          <div><strong>Chain jump available</strong><span>Continue capturing, or end your turn.</span></div>
          <button type="button" @click="client?.sendEndJump()">End jump</button>
        </div>
      </section>

      <aside class="side-panel" :class="{ 'side-panel--open': rulesOpen }">
        <button class="side-panel__close" type="button" aria-label="Close rules" @click="rulesOpen = false">×</button>
        <section>
          <h3>How to play</h3>
          <ol>
            <li><b>Overlings</b> move one square in any direction, or jump an adjacent piece into an empty square.</li>
            <li>Jump an enemy to capture it. You may keep jumping with the same Overling.</li>
            <li><b>Underlings</b> move one square and capture an enemy only on a diagonal.</li>
            <li>Reach the far edge with an Underling to exchange a captured Overling back into play.</li>
            <li>Remove every enemy piece to win.</li>
          </ol>
        </section>
        <section v-if="!isViewer" class="reserve">
          <h3>Your reserve</h3>
          <div class="reserve__pieces">
            <i v-for="token in myPlayer?.capturedOverlings ?? 0" :key="token" :class="pieceColorClass(myColor)" />
            <span v-if="!myPlayer?.capturedOverlings">No captured Overlings yet</span>
          </div>
          <p>Reserved Overlings can replace an Underling that reaches the opposite edge.</p>
        </section>
        <BacklashCrowdPanel
          :viewer="isViewer"
          :viewer-count="state.viewerCount"
          :viewers="state.viewers"
          :disabled="!encouragementReady || !matchIsLive"
          @encourage="sendEncouragement"
        />
        <section class="match-meta">
          <span>Move {{ state.moveCount }}</span><span>Room {{ shortRoomId }}</span>
        </section>
      </aside>

      <aside class="player-card player-card--me" :class="playerCardClass(bottomPlayer)">
        <div class="player-card__token" :class="pieceColorClass(bottomPlayer?.color)">
          {{ initials(bottomPlayer?.name) }}
        </div>
        <div class="player-card__copy">
          <span class="player-card__label">{{ isViewer ? bottomColorLabel : `You · ${bottomPlayerColorLabel}` }}</span>
          <strong>{{ bottomPlayer?.name || 'You' }}</strong>
          <span class="player-card__status"><i :class="{ offline: bottomPlayer && !bottomPlayer.connected }" />{{ bottomPlayer?.connected ? 'Ready' : 'Reconnecting' }}</span>
        </div>
        <div class="player-card__score">
          <strong>{{ pieceTotal(bottomPlayer?.color) }}</strong><span>pieces</span>
        </div>
      </aside>
    </section>

    <v-dialog :model-value="showPromotion" persistent max-width="430">
      <section class="decision-card">
        <div class="decision-card__icon"><span :class="pieceColorClass(myColor)">B</span></div>
        <div class="decision-card__eyebrow">UNDERLING REACHED THE FAR EDGE</div>
        <h2>Bring back an Overling?</h2>
        <p>Exchange one captured Overling from your reserve. If you skip, the Underling stays in play.</p>
        <div class="decision-card__actions">
          <v-btn variant="text" @click="client?.sendPromotion(false)">Keep Underling</v-btn>
          <v-btn color="deep-orange-darken-2" @click="client?.sendPromotion(true)">Restore Overling</v-btn>
        </div>
      </section>
    </v-dialog>

    <v-dialog :model-value="showResult" persistent max-width="470">
      <section class="result-card" :class="`result-card--${resultTone}`">
        <div class="result-card__burst" aria-hidden="true" />
        <div class="result-card__symbol">{{ resultSymbol }}</div>
        <div class="result-card__eyebrow">MATCH COMPLETE</div>
        <h2>{{ resultTitle }}</h2>
        <p>{{ resultDescription }}</p>
        <div class="result-card__stats">
          <span><strong>{{ state?.moveCount ?? 0 }}</strong> moves</span>
          <span><strong>{{ pieceTotal(bottomColor) }}</strong> pieces left</span>
        </div>
        <div class="result-card__actions">
          <v-btn variant="text" @click="leaveGame">Exit</v-btn>
          <v-btn v-if="!isViewer" color="deep-orange-darken-2" :disabled="rematchUnavailable" @click="requestRematch">
            {{ rematchButtonLabel }}
          </v-btn>
        </div>
      </section>
    </v-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  BACKLASH_BOARD_SIZE,
  countPieces,
  legalMovesForPiece,
  type BacklashBoard,
  type BacklashColor,
  type BacklashPiece,
} from '@shared/minigames/backlash'
import {
  BACKLASH_ENCOURAGEMENT_COOLDOWN_MS,
  isBacklashLivePhase,
  type BacklashEncouragement,
} from '@shared/minigames/backlashSocial'
import { useAuthStore } from '@/stores/auth'
import { useMinigamesStore } from '@/stores/minigames'
import BacklashCrowdPanel from '@/components/backlash/BacklashCrowdPanel.vue'
import {
  BacklashRoomClient,
  type BacklashEncouragementEvent,
  type BacklashPlayerSnapshot,
  type BacklashSnapshot,
} from '@/multiplayer/BacklashRoomClient'
import {
  findCapturedBacklashPieces,
  findRemovedBacklashPieces,
} from './backlashPresentation'

const props = defineProps<{ roomId: string }>()
const router = useRouter()
const auth = useAuthStore()
const minigames = useMinigamesStore()
const client = ref<BacklashRoomClient | null>(null)
const state = ref<BacklashSnapshot | null>(null)
const loading = ref(true)
const error = ref('')
const connectionStatus = ref<'connected' | 'reconnecting' | 'disconnected'>('connected')
const roomClosed = ref(false)
const selectedIndex = ref<number | null>(null)
const rulesOpen = ref(false)
const nowMs = ref(Date.now())
const captureEffects = ref<CaptureEffect[]>([])
const encouragementVisuals = ref<EncouragementVisual[]>([])
const encouragementReady = ref(true)
const captureEffectTimers = new Set<number>()
const encouragementTimers = new Set<number>()
const ENCOURAGEMENT_VISUAL_MS = 2_200
let encouragementCooldownTimer: number | null = null
let clockTimer: number | null = null

interface CaptureEffect {
  key: string
  index: number
  piece: BacklashPiece
}

interface EncouragementVisual extends BacklashEncouragementEvent {
  key: string
  slot: number
}

const myPlayer = computed(() => state.value?.players.find((player) => player.userId === auth.user?.id))
const otherPlayer = computed(() => state.value?.players.find((player) => player.userId !== auth.user?.id))
const myColor = computed<BacklashColor | null>(() => myPlayer.value?.color ?? null)
const isViewer = computed(() => Boolean(state.value && !myPlayer.value))
const bottomColor = computed<BacklashColor>(() => myColor.value ?? 'white')
const topColor = computed<BacklashColor>(() => bottomColor.value === 'white' ? 'black' : 'white')
const topColorLabel = computed(() => `${capitalize(topColor.value)} side`)
const bottomColorLabel = computed(() => `${capitalize(bottomColor.value)} side`)
const topPlayer = computed(() => (
  state.value?.players.find((player) => player.color === topColor.value)
  ?? (isViewer.value ? state.value?.players[0] : otherPlayer.value)
))
const bottomPlayer = computed(() => (
  state.value?.players.find((player) => player.color === bottomColor.value)
  ?? (isViewer.value ? state.value?.players[1] : myPlayer.value)
))
const bottomPlayerColorLabel = computed(() => (
  bottomPlayer.value?.color ? `${capitalize(bottomPlayer.value.color)} side` : 'Unassigned'
))
const turnPlayer = computed(() => state.value?.players.find((player) => player.userId === state.value?.turnUserId))
const isMyTurn = computed(() => state.value?.turnUserId === auth.user?.id)
const matchIsLive = computed(() => Boolean(
  state.value && isBacklashLivePhase(state.value.phase),
))
const canInteract = computed(() => Boolean(
  state.value
  && isMyTurn.value
  && connectionStatus.value === 'connected'
  && (state.value.phase === 'playing' || state.value.phase === 'jump'),
))
const displayIndices = computed(() => Array.from({ length: BACKLASH_BOARD_SIZE ** 2 }, (_, index) =>
  bottomColor.value === 'white' ? BACKLASH_BOARD_SIZE ** 2 - 1 - index : index,
))
const shortRoomId = computed(() => props.roomId.length > 10 ? `${props.roomId.slice(0, 8)}…` : props.roomId)
const showPromotion = computed(() => state.value?.phase === 'promotion' && isMyTurn.value)
const showResult = computed(() => state.value?.phase === 'finished')
const rematchUnavailable = computed(() => roomClosed.value || Boolean(myPlayer.value?.rematchReady))
const rematchButtonLabel = computed(() => {
  if (roomClosed.value) return 'Rematch window expired'
  return myPlayer.value?.rematchReady ? 'Waiting for opponent…' : 'Play again'
})
const turnSeconds = computed(() => {
  if (!state.value?.turnDeadlineMs || state.value.phase === 'finished' || state.value.phase === 'lobby') return null
  return Math.max(0, Math.ceil((state.value.turnDeadlineMs - nowMs.value) / 1000))
})
const turnHint = computed(() => {
  if (state.value?.phase === 'jump') return 'Continue with the highlighted Overling'
  if (selectedIndex.value !== null) return 'Choose a highlighted destination'
  return 'Choose one of your pieces'
})

const legalTargetSet = computed(() => {
  const snapshot = state.value
  if (!snapshot || !canInteract.value) return new Set<number>()
  if (snapshot.phase === 'jump') return new Set(snapshot.legalTargets)
  if (selectedIndex.value === null) return new Set<number>()
  return new Set(legalMovesForPiece(snapshot.board, selectedIndex.value).map((move) => move.to))
})

const positionedPieces = computed(() => {
  const snapshot = state.value
  if (!snapshot) return []
  return snapshot.board.flatMap((piece, index) => {
    if (!piece) return []
    return [{
      index,
      piece,
      style: positionStyle(index),
    }]
  })
})

const removedTopPieces = computed(() => (
  findRemovedBacklashPieces(state.value?.board, topPlayer.value?.color)
))
const removedBottomPieces = computed(() => (
  findRemovedBacklashPieces(state.value?.board, bottomPlayer.value?.color)
))
const positionedCaptureEffects = computed(() => captureEffects.value.map((effect) => ({
  ...effect,
  style: positionStyle(effect.index),
})))

const resultTone = computed(() => {
  if (!state.value || state.value.outcome === 'draw') return 'draw'
  if (isViewer.value) return 'spectator'
  return state.value.winnerId === auth.user?.id ? 'win' : 'loss'
})
const winner = computed(() => state.value?.players.find((player) => player.userId === state.value?.winnerId))
const resultSymbol = computed(() => resultTone.value === 'win' ? '✦' : resultTone.value === 'draw' ? '◇' : resultTone.value === 'spectator' ? '●' : '◆')
const resultTitle = computed(() => {
  if (resultTone.value === 'spectator') return winner.value ? `${winner.value.name} wins` : 'Match complete'
  return resultTone.value === 'win' ? 'Brilliant victory' : resultTone.value === 'draw' ? 'Honours even' : 'Outmanoeuvred'
})
const resultDescription = computed(() => {
  if (isViewer.value) return 'Thanks for watching and cheering the players on.'
  const reason = state.value?.outcomeReason ?? ''
  const descriptions: Record<string, string> = {
    all_pieces: resultTone.value === 'win' ? 'You took every opposing piece.' : 'Your final piece was captured.',
    no_legal_moves: resultTone.value === 'win' ? 'Your opponent had no legal move.' : 'No legal move remained.',
    timeout: resultTone.value === 'win' ? 'Your opponent ran out of time.' : 'Your turn timer expired.',
    disconnect: resultTone.value === 'win' ? 'Your opponent did not reconnect.' : 'The reconnect window expired.',
    repetition: 'The same board position occurred three times.',
    no_progress: 'Neither side captured or restored a piece for 100 turns.',
  }
  return descriptions[reason] ?? 'The match has ended.'
})

watch(() => state.value?.revision, () => {
  const locked = state.value?.lockedJumpIndex ?? -1
  selectedIndex.value = locked >= 0 ? locked : null
})

onMounted(async () => {
  clockTimer = window.setInterval(() => { nowMs.value = Date.now() }, 250)
  try {
    if (!auth.user) await auth.fetchUser()
    const user = auth.user
    if (!user || !auth.token) throw new Error('Please sign in again to join this match.')
    const roomClient = new BacklashRoomClient()
    client.value = roomClient
    roomClient.onStateChange = (snapshot) => {
      animateCapturedPieces(state.value?.board, snapshot.board, snapshot.revision)
      state.value = snapshot
      loading.value = false
      if (snapshot.phase === 'finished') void minigames.fetchStatus()
    }
    roomClient.onConnectionChange = (status) => { connectionStatus.value = status }
    roomClient.onError = (reason) => { error.value = humanizeReason(reason) }
    roomClient.onClosed = (reason) => {
      roomClosed.value = true
      connectionStatus.value = 'disconnected'
      if (state.value?.phase !== 'finished') error.value = humanizeReason(reason)
    }
    roomClient.onEncouragement = showEncouragement
    await roomClient.joinById(props.roomId, {
      userId: user.id,
      name: user.name,
      orgId: user.org_id,
      token: auth.token,
    })
  } catch (cause) {
    loading.value = false
    error.value = cause instanceof Error ? cause.message : 'Could not join this Backlash match.'
  }
})

onBeforeUnmount(() => {
  if (clockTimer !== null) window.clearInterval(clockTimer)
  for (const timer of captureEffectTimers) window.clearTimeout(timer)
  captureEffectTimers.clear()
  for (const timer of encouragementTimers) window.clearTimeout(timer)
  encouragementTimers.clear()
  if (encouragementCooldownTimer !== null) window.clearTimeout(encouragementCooldownTimer)
  client.value?.destroy()
})

function animateCapturedPieces(
  previousBoard: BacklashBoard | undefined,
  nextBoard: BacklashBoard,
  revision: number,
): void {
  for (const { piece, index } of findCapturedBacklashPieces(previousBoard, nextBoard)) {
    const key = `${revision}-${piece.id}`
    captureEffects.value.push({ key, index, piece })
    const timer = window.setTimeout(() => {
      captureEffects.value = captureEffects.value.filter((effect) => effect.key !== key)
      captureEffectTimers.delete(timer)
    }, 720)
    captureEffectTimers.add(timer)
  }
}

function positionStyle(index: number): { transform: string } {
  const physicalIndex = bottomColor.value === 'white'
    ? BACKLASH_BOARD_SIZE ** 2 - 1 - index
    : index
  const row = Math.floor(physicalIndex / BACKLASH_BOARD_SIZE)
  const column = physicalIndex % BACKLASH_BOARD_SIZE
  return { transform: `translate(${column * 100}%, ${row * 100}%)` }
}

function showEncouragement(event: BacklashEncouragementEvent): void {
  const key = `${event.id}-${event.createdAtMs}`
  encouragementVisuals.value.push({
    ...event,
    key,
    slot: encouragementVisuals.value.length % 4,
  })
  const timer = window.setTimeout(() => {
    encouragementVisuals.value = encouragementVisuals.value.filter((item) => item.key !== key)
    encouragementTimers.delete(timer)
  }, ENCOURAGEMENT_VISUAL_MS)
  encouragementTimers.add(timer)
}

function sendEncouragement(reaction: BacklashEncouragement): void {
  if (!encouragementReady.value || !matchIsLive.value) return
  encouragementReady.value = false
  client.value?.sendEncouragement(reaction)
  if (encouragementCooldownTimer !== null) window.clearTimeout(encouragementCooldownTimer)
  encouragementCooldownTimer = window.setTimeout(() => {
    encouragementReady.value = true
    encouragementCooldownTimer = null
  }, BACKLASH_ENCOURAGEMENT_COOLDOWN_MS)
}

function selectSquare(index: number): void {
  const snapshot = state.value
  if (!snapshot || !canInteract.value) return
  if (legalTargetSet.value.has(index)) {
    const from = snapshot.phase === 'jump' ? snapshot.lockedJumpIndex : selectedIndex.value
    if (from !== null && from >= 0) client.value?.sendMove(from, index, snapshot.revision)
    return
  }
  if (snapshot.phase === 'jump') return
  const piece = snapshot.board[index]
  selectedIndex.value = piece?.color === myColor.value
    ? (selectedIndex.value === index ? null : index)
    : null
}

function squareClasses(index: number): Record<string, boolean> {
  const row = Math.floor(index / BACKLASH_BOARD_SIZE)
  const column = index % BACKLASH_BOARD_SIZE
  return {
    'square--dark': (row + column) % 2 === 1,
    'square--selected': selectedIndex.value === index,
    'square--legal': legalTargetSet.value.has(index),
  }
}

function squareLabel(index: number): string {
  const piece = state.value?.board[index]
  const row = Math.floor(index / BACKLASH_BOARD_SIZE) + 1
  const column = String.fromCharCode(65 + (index % BACKLASH_BOARD_SIZE))
  return piece ? `${column}${row}: ${piece.color} ${piece.kind}` : `${column}${row}: empty`
}

function pieceTotal(color: BacklashColor | null | undefined): number {
  return color && state.value ? countPieces(state.value.board, color) : 0
}

function playerCardClass(player: BacklashPlayerSnapshot | undefined): Record<string, boolean> {
  return {
    'player-card--active': Boolean(player && state.value?.turnUserId === player.userId && state.value.phase !== 'finished'),
    'player-card--offline': Boolean(player && !player.connected),
  }
}

function pieceColorClass(color: BacklashColor | null | undefined): string {
  return color === 'black' ? 'token--black' : 'token--white'
}

function initials(name: string | undefined): string {
  const parts = (name ?? '?').trim().split(/\s+/).filter(Boolean)
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || '?'
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function humanizeReason(reason: string): string {
  const messages: Record<string, string> = {
    stale_or_invalid_move: 'The board changed before that move arrived. Please try again.',
    invalid_move: 'That move is not legal.',
    wrong_turn: 'Wait for your turn.',
    jump_piece_locked: 'Continue with the same Overling or end the jump.',
    cannot_end_jump: 'There is no jump chain to end.',
    cannot_resolve_promotion: 'That promotion is no longer available.',
    declined: 'Your opponent declined the challenge.',
    expired: 'This challenge expired.',
    cancelled: 'The host cancelled this challenge.',
    player_left: 'The other player left before the match began.',
    rematch_expired: 'The rematch window expired.',
    room_closed: 'This match room has closed.',
  }
  return messages[reason] ?? reason.replace(/_/g, ' ')
}

function requestRematch(): void {
  client.value?.sendRematch()
}

async function leaveGame(): Promise<void> {
  if (state.value?.phase === 'lobby' && state.value.hostUserId === auth.user?.id) {
    client.value?.sendCancel()
  }
  await router.push({ name: 'dashboard' })
}
</script>

<style scoped>
.backlash-shell {
  --cream: #f5ead3; --copper: #bd5735; --ink: #160f0c;
  position: relative; min-height: calc(100vh - 64px); overflow: hidden; padding: 18px 28px 32px;
  color: var(--cream); background:
    linear-gradient(rgba(18,10,7,.95), rgba(28,12,9,.98)),
    repeating-linear-gradient(90deg, #301b12 0 80px, #25140e 80px 160px);
}
.ambient { position: absolute; width: 420px; aspect-ratio: 1; border-radius: 50%; filter: blur(90px); opacity: .16; pointer-events: none; }
.ambient--one { right: -100px; top: 10%; background: #d65d38; }
.ambient--two { left: -180px; bottom: -120px; background: #ad793e; }
.topbar { position: relative; z-index: 2; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; max-width: 1180px; margin: 0 auto 18px; }
.brand { text-align: center; font-family: Georgia, serif; letter-spacing: .18em; }
.brand span { display: block; font-size: clamp(24px, 3vw, 38px); }
.brand small { display: block; margin-top: -2px; color: rgba(245,234,211,.55); font-size: 9px; letter-spacing: .08em; }
.back-button, .rules-button { display: inline-flex; align-items: center; gap: 6px; width: max-content; border: 1px solid rgba(255,255,255,.12); border-radius: 9px; padding: 8px 11px; background: rgba(0,0,0,.2); color: rgba(245,234,211,.75); cursor: pointer; }
.rules-button { justify-self: end; }
.connection-banner, .error-alert { position: relative; z-index: 5; max-width: 760px; margin: 0 auto 12px; }
.connection-banner { display: flex; justify-content: center; align-items: center; gap: 8px; padding: 8px 14px; border: 1px solid rgba(255,183,77,.35); border-radius: 9px; background: rgba(82,46,16,.9); font-size: 12px; }
.loading-panel { position: relative; z-index: 1; display: grid; place-items: center; max-width: 520px; margin: 12vh auto; text-align: center; }
.loading-panel h2 { margin: 18px 0 2px; font-family: Georgia, serif; }
.loading-panel p { margin: 0; opacity: .6; }
.loading-piece { width: 64px; height: 64px; border: 6px solid #362b25; border-radius: 50%; background: #111; animation: loading-hop 1s ease-in-out infinite; box-shadow: 0 12px 25px #000; }
@keyframes loading-hop { 50% { transform: translateY(-12px) rotate(12deg); } }
.game-layout { position: relative; z-index: 1; display: grid; grid-template-columns: minmax(170px, 220px) minmax(420px, 680px) minmax(190px, 250px); grid-template-areas: "opponent table side" "me table side"; gap: 16px 24px; align-items: start; justify-content: center; max-width: 1220px; margin: auto; }
.player-card { grid-area: opponent; display: grid; grid-template-columns: 46px 1fr auto; gap: 11px; align-items: center; padding: 12px; border: 1px solid rgba(255,255,255,.1); border-radius: 13px; background: rgba(12,8,6,.68); opacity: .82; transition: border-color .2s, box-shadow .2s, transform .2s; }
.player-card--me { grid-area: me; align-self: end; }
.player-card--active { opacity: 1; transform: translateX(4px); border-color: rgba(222,145,72,.65); box-shadow: 0 0 24px rgba(196,81,42,.2); }
.player-card--offline { opacity: .5; }
.player-card__token { display: grid; place-items: center; width: 44px; height: 44px; border: 3px solid; border-radius: 50%; font-weight: 900; font-size: 12px; }
.token--white { background: linear-gradient(145deg, #fff9eb, #cfc3ad); border-color: #fffdf6; color: #352b25; }
.token--black { background: linear-gradient(145deg, #37322f, #0c0b0a); border-color: #504944; color: #f2e8d7; }
.player-card__copy { display: flex; flex-direction: column; min-width: 0; }
.player-card__copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.player-card__label { color: #d89b5b; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; }
.player-card__status { display: flex; align-items: center; gap: 5px; color: rgba(245,234,211,.52); font-size: 10px; }
.player-card__status i { width: 6px; height: 6px; border-radius: 50%; background: #70d57c; }
.player-card__status i.offline { background: #e67960; }
.player-card__score { display: flex; flex-direction: column; text-align: right; }
.player-card__score strong { font-size: 20px; }
.player-card__score span { opacity: .45; font-size: 9px; }
.table-area { grid-area: table; min-width: 0; }
.turn-strip { display: grid; grid-template-columns: minmax(48px, 1fr) auto minmax(48px, 1fr); align-items: center; min-height: 39px; padding: 0 12px; margin-bottom: 9px; border: 1px solid rgba(255,255,255,.1); border-radius: 10px; background: rgba(0,0,0,.25); color: rgba(245,234,211,.68); font-size: 12px; }
.turn-strip--mine { border-color: rgba(215,131,59,.48); color: #ffe1b8; }
.turn-strip__content { grid-column: 2; display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-width: 0; text-align: center; }
.turn-pulse { width: 7px; height: 7px; border-radius: 50%; background: #ef9b54; box-shadow: 0 0 0 0 rgba(239,155,84,.6); animation: pulse 1.6s infinite; }
@keyframes pulse { 70% { box-shadow: 0 0 0 7px transparent; } }
.turn-strip__hint { opacity: .56; }
.turn-clock { grid-column: 3; justify-self: end; min-width: 34px; text-align: right; font-weight: 900; font-variant-numeric: tabular-nums; }
.turn-clock.urgent { color: #ff735b; animation: clock-pulse .65s infinite alternate; }
@keyframes clock-pulse { to { transform: scale(1.1); } }
.board-frame { position: relative; padding: clamp(20px, 3.2vw, 38px); border: 2px solid #8c5432; border-radius: 9px; background: linear-gradient(100deg, #62351e, #a5683e 48%, #5a2f1d); box-shadow: 0 28px 55px rgba(0,0,0,.55), inset 0 0 0 5px rgba(42,20,11,.35); }
.wood-grain { position: absolute; inset: 0; opacity: .17; background: repeating-linear-gradient(3deg, transparent 0 16px, #1d0e08 17px, transparent 19px); pointer-events: none; }
.board { position: relative; display: grid; grid-template-columns: repeat(8, 1fr); overflow: hidden; aspect-ratio: 1; border: 3px solid #2d180f; background: #d0a474; box-shadow: inset 0 0 22px rgba(36,17,9,.35); }
.square { position: relative; aspect-ratio: 1; border: 0; border-right: 1px solid rgba(45,24,15,.38); border-bottom: 1px solid rgba(45,24,15,.38); background: rgba(232,201,158,.76); cursor: pointer; }
.square--dark { background: rgba(146,94,56,.78); }
.square:disabled { cursor: default; }
.square--selected { box-shadow: inset 0 0 0 4px rgba(255,194,91,.75); }
.square--legal { background-image: radial-gradient(circle, rgba(255,209,112,.2), transparent 65%); }
.legal-dot { position: absolute; z-index: 4; inset: 50% auto auto 50%; width: 24%; aspect-ratio: 1; transform: translate(-50%,-50%); border-radius: 50%; background: #ffd17a; box-shadow: 0 0 0 4px rgba(57,29,16,.28), 0 0 16px rgba(255,184,79,.72); animation: target-breathe .9s infinite alternate; }
@keyframes target-breathe { to { transform: translate(-50%,-50%) scale(1.18); } }
.piece { position: absolute; z-index: 3; top: 0; left: 0; width: 12.5%; height: 12.5%; padding: .75%; pointer-events: none; transition: transform .34s cubic-bezier(.2,.82,.24,1), opacity .22s, filter .2s; }
.piece::before { content: ''; position: absolute; inset: 14%; border-radius: 50%; box-shadow: 0 7px 9px rgba(37,15,7,.55), inset 0 -5px 9px rgba(0,0,0,.28), inset 0 3px 5px rgba(255,255,255,.2); }
.piece--white::before { border: 3px solid #fffaf0; background: linear-gradient(145deg, #fff7e7, #c9bca6); }
.piece--black::before { border: 3px solid #3c3734; background: linear-gradient(145deg, #302c2a, #080706); }
.piece__rim { position: absolute; z-index: 1; inset: 25%; border: 1px dashed rgba(133,90,53,.45); border-radius: 50%; }
.piece--black .piece__rim { border-color: rgba(255,255,255,.15); }
.piece__crown { position: absolute; z-index: 2; inset: 0; display: grid; place-items: center; font-family: Georgia, serif; font-size: clamp(10px, 1.45vw, 20px); font-weight: 900; color: #75482f; }
.piece--black .piece__crown { color: #c0ad94; }
.piece--selected { filter: drop-shadow(0 0 8px #ffc762); animation: selected-float .65s infinite alternate; }
@keyframes selected-float { to { margin-top: -3px; } }
.capture-effect { position: absolute; z-index: 8; top: 0; left: 0; width: 12.5%; height: 12.5%; pointer-events: none; }
.capture-effect__coin { position: absolute; z-index: 2; inset: 14%; display: grid; place-items: center; border: 3px solid; border-radius: 50%; font-family: Georgia, serif; font-weight: 900; box-shadow: 0 7px 13px rgba(32,12,6,.58); animation: captured-away .72s cubic-bezier(.22,.78,.22,1) forwards; }
.capture-effect__coin--white { border-color: #fffaf0; background: linear-gradient(145deg, #fff7e7, #c9bca6); color: #75482f; }
.capture-effect__coin--black { border-color: #3c3734; background: linear-gradient(145deg, #302c2a, #080706); color: #c0ad94; }
.capture-effect__burst { position: absolute; z-index: 1; inset: 8%; border: 2px solid #ffd078; border-radius: 50%; animation: capture-burst .55s ease-out forwards; }
@keyframes captured-away { 0% { opacity: 1; transform: scale(1); } 42% { opacity: 1; transform: translateY(-16%) scale(1.18) rotate(-8deg); } 100% { opacity: 0; transform: translateY(-92%) scale(.35) rotate(42deg); } }
@keyframes capture-burst { from { opacity: .9; transform: scale(.45); } to { opacity: 0; transform: scale(1.8); } }
.capture-rack { display: flex; align-items: center; gap: 8px; min-height: 30px; padding: 4px 9px; border: 1px solid rgba(255,255,255,.08); border-radius: 8px; background: rgba(0,0,0,.18); }
.capture-rack--opponent { margin-bottom: 8px; }.capture-rack--mine { margin-top: 8px; }
.capture-rack__label { flex: 0 0 auto; color: rgba(245,234,211,.48); font-size: 8px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.capture-rack__pieces { display: flex; flex: 1; flex-wrap: wrap; gap: 3px; min-width: 0; }
.capture-rack__empty { margin-left: auto; color: rgba(245,234,211,.28); font-size: 9px; }
.capture-token { display: grid; place-items: center; width: 20px; height: 20px; border: 2px solid; border-radius: 50%; font-family: Georgia, serif; font-size: 9px; box-shadow: 0 3px 6px rgba(0,0,0,.4); }
.capture-token--white { border-color: #fffaf0; background: linear-gradient(145deg, #fff7e7, #c9bca6); color: #75482f; }
.capture-token--black { border-color: #4d4742; background: linear-gradient(145deg, #302c2a, #080706); color: #c0ad94; }
.capture-token--underling { transform: scale(.82); }
.captured-token-enter-active { animation: captured-token-in .42s cubic-bezier(.18,.86,.24,1.3); }
@keyframes captured-token-in { from { opacity: 0; transform: translateY(-12px) scale(.35) rotate(-24deg); } }
.crowd-reaction { position: absolute; z-index: 12; right: 7%; bottom: 8%; display: flex; flex-direction: column; align-items: center; pointer-events: none; filter: drop-shadow(0 7px 9px rgba(0,0,0,.45)); animation: crowd-float 2.2s ease-out forwards; }
.crowd-reaction strong { font-size: clamp(30px, 4vw, 54px); line-height: 1; }
.crowd-reaction span { max-width: 110px; overflow: hidden; color: #fff5dd; font-size: 9px; font-weight: 800; text-overflow: ellipsis; white-space: nowrap; }
.crowd-reaction--1 { right: 22%; bottom: 14%; }.crowd-reaction--2 { right: 10%; bottom: 27%; }.crowd-reaction--3 { right: 30%; bottom: 5%; }
@keyframes crowd-float { 0% { opacity: 0; transform: translateY(18px) scale(.5) rotate(-8deg); } 18% { opacity: 1; transform: translateY(0) scale(1.12) rotate(4deg); } 72% { opacity: 1; } 100% { opacity: 0; transform: translateY(-80px) scale(.82) rotate(-4deg); } }
.board-mark { position: absolute; left: 50%; transform: translateX(-50%); color: rgba(255,235,205,.62); font-size: 8px; font-weight: 900; letter-spacing: .16em; text-transform: uppercase; }
.board-mark--top { top: 8px; }.board-mark--bottom { bottom: 8px; }
.board-frame--locked .board { filter: saturate(.76); }
.chain-panel { display: flex; align-items: center; gap: 14px; margin-top: 9px; padding: 10px 12px; border: 1px solid rgba(225,142,65,.38); border-radius: 10px; background: rgba(85,40,20,.62); }
.chain-panel div { display: flex; flex-direction: column; flex: 1; font-size: 12px; }.chain-panel div span { opacity: .58; font-size: 10px; }
.chain-panel button { border: 1px solid rgba(255,255,255,.2); border-radius: 7px; padding: 7px 11px; background: rgba(0,0,0,.2); color: white; cursor: pointer; }
.side-panel { grid-area: side; display: flex; flex-direction: column; gap: 14px; }
.side-panel__close { display: none; }
.side-panel section { padding: 15px; border: 1px solid rgba(255,255,255,.09); border-radius: 12px; background: rgba(11,7,5,.55); }
.side-panel h3 { margin: 0 0 9px; color: #dca064; font-family: Georgia, serif; font-size: 15px; }
.side-panel ol { display: flex; flex-direction: column; gap: 7px; margin: 0; padding-left: 18px; color: rgba(245,234,211,.62); font-size: 10px; line-height: 1.42; }
.side-panel li::marker { color: #c6623f; font-weight: 900; }
.reserve__pieces { display: flex; flex-wrap: wrap; gap: 4px; min-height: 24px; align-items: center; }
.reserve__pieces i { display: block; width: 22px; height: 22px; border: 2px solid; border-radius: 50%; }
.reserve__pieces span, .reserve p { color: rgba(245,234,211,.45); font-size: 9px; }.reserve p { margin: 8px 0 0; }
.match-meta { display: flex; justify-content: space-between; color: rgba(245,234,211,.38); font-size: 9px; }
.decision-card, .result-card { position: relative; overflow: hidden; padding: 28px; border: 1px solid rgba(224,150,81,.35); border-radius: 19px; background: linear-gradient(150deg, #21130e, #55231b); color: #fff4de; text-align: center; }
.decision-card__icon > span { display: grid; place-items: center; width: 66px; height: 66px; margin: auto; border: 5px solid; border-radius: 50%; font-family: Georgia, serif; font-size: 26px; font-weight: 900; box-shadow: 0 14px 25px rgba(0,0,0,.4); }
.decision-card__eyebrow, .result-card__eyebrow { margin-top: 18px; color: #e0a260; font-size: 9px; font-weight: 900; letter-spacing: .16em; }
.decision-card h2, .result-card h2 { margin: 4px 0 7px; font-family: Georgia, serif; }.decision-card p, .result-card p { margin: 0; color: rgba(255,244,222,.58); font-size: 12px; }
.decision-card__actions, .result-card__actions { display: flex; justify-content: center; gap: 8px; margin-top: 22px; }
.result-card__symbol { position: relative; z-index: 1; display: grid; place-items: center; width: 72px; height: 72px; margin: auto; border: 2px solid #e1a160; border-radius: 50%; color: #ffd59d; font-size: 42px; box-shadow: 0 0 40px rgba(222,142,62,.28); animation: result-in .55s cubic-bezier(.2,.9,.2,1); }
@keyframes result-in { from { opacity: 0; transform: scale(.35) rotate(-30deg); } }
.result-card__burst { position: absolute; width: 280px; height: 280px; left: 50%; top: -80px; transform: translateX(-50%); background: repeating-conic-gradient(from 0deg, rgba(221,137,58,.09) 0 8deg, transparent 8deg 18deg); animation: burst-spin 14s linear infinite; }
@keyframes burst-spin { to { transform: translateX(-50%) rotate(360deg); } }
.result-card--loss { filter: saturate(.68); }.result-card--draw, .result-card--spectator { background: linear-gradient(150deg, #191715, #3c3831); }
.result-card__stats { display: grid; grid-template-columns: 1fr 1fr; margin-top: 20px; border-block: 1px solid rgba(255,255,255,.09); }
.result-card__stats span { display: flex; flex-direction: column; padding: 10px; color: rgba(255,244,222,.48); font-size: 9px; text-transform: uppercase; }.result-card__stats strong { color: #fff1d5; font-size: 17px; }
@media (max-width: 980px) {
  .game-layout { grid-template-columns: minmax(420px, 680px) 220px; grid-template-areas: "opponent side" "table side" "me side"; }
  .player-card { max-width: 420px; }.player-card--active { transform: translateY(-2px); }
}
@media (max-width: 760px) {
  .backlash-shell { padding: 12px 10px 24px; }.topbar { grid-template-columns: auto 1fr auto; }.brand small { display: none; }
  .game-layout { display: flex; flex-direction: column; align-items: stretch; }.player-card { width: 100%; max-width: none; order: 1; }.table-area { order: 2; }.player-card--me { order: 3; }
  .side-panel { position: fixed; z-index: 20; inset: 0 0 0 auto; width: min(320px, 88vw); padding: 54px 18px 18px; overflow-y: auto; background: #1b100c; transform: translateX(105%); transition: transform .25s; box-shadow: -20px 0 45px rgba(0,0,0,.5); }
  .side-panel--open { transform: translateX(0); }.side-panel__close { display: block; position: absolute; top: 12px; right: 18px; border: 0; background: transparent; color: white; font-size: 28px; }
  .board-frame { padding: 25px; }.turn-strip__hint { display: none; }
}
@media (max-width: 430px) {
  .brand span { font-size: 19px; }.back-button, .rules-button { font-size: 0; }.back-button .v-icon, .rules-button .v-icon { font-size: 20px; }
  .board-frame { padding: 18px; }.board-mark { display: none; }.player-card { padding: 9px; }.piece::before { border-width: 2px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
</style>
