<script setup lang="ts">
/**
 * RaceHUD — orchestrator overlay for the race scene.
 *
 * Reads a live snapshot from RaceEngine.getHudState() inside a
 * requestAnimationFrame loop. Each phase delegates to a focused
 * subcomponent so this file stays thin.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { RaceEngine, RaceHudState } from '@/engine/race'
import RaceHudRunningPanel from './RaceHudRunningPanel.vue'
import RaceHudResultsPanel from './RaceHudResultsPanel.vue'

const props = defineProps<{ engine: RaceEngine }>()

const state = ref<RaceHudState | null>(null)
let rafHandle: number | null = null

function pollFrame(): void {
  state.value = props.engine.getHudState()
  rafHandle = requestAnimationFrame(pollFrame)
}

onMounted(() => pollFrame())
onUnmounted(() => {
  if (rafHandle !== null) cancelAnimationFrame(rafHandle)
  rafHandle = null
})

const phase = computed(() => state.value?.phase ?? 'lobby')
const slots = computed(() => state.value?.slots ?? [])
const countdownLabel = computed(() => {
  const remain = state.value?.countdownRemainingMs ?? 0
  return remain <= 0 ? 'GO!' : String(Math.ceil(remain / 1000))
})
</script>

<template>
  <div class="race-hud" v-if="state">
    <!-- Lobby -->
    <div v-if="phase === 'lobby'" class="panel panel--lobby">
      <h2>Pavilion Sprint</h2>
      <p>Hold your <strong>move</strong> key to join. <strong>Tap Shift</strong> rapidly during the race to sprint.</p>
      <ul class="slot-list">
        <li v-for="(slot, i) in slots" :key="i" :class="{ joined: slot.joined }">
          <span class="slot-keys">
            <span class="slot-key">{{ slot.moveLabel }}</span>
            <span class="slot-sep">+</span>
            <span class="slot-key slot-key--sprint">{{ slot.sprintLabel }}</span>
          </span>
          <span class="slot-name">{{ slot.name }}</span>
          <span class="slot-status">{{ slot.joined ? 'joined' : 'waiting…' }}</span>
        </li>
      </ul>
      <p class="keys-hint">move + sprint</p>
    </div>

    <!-- Countdown -->
    <div v-else-if="phase === 'countdown'" class="panel panel--countdown">
      <div class="countdown-number">{{ countdownLabel }}</div>
      <p class="countdown-hint">Hold your move key!</p>
    </div>

    <!-- Running -->
    <RaceHudRunningPanel
      v-else-if="phase === 'running'"
      :elapsed-ms="state.runningElapsedMs"
      :track-length-m="state.trackLengthM"
      :slots="slots"
    />

    <!-- Finished -->
    <RaceHudResultsPanel
      v-else-if="phase === 'finished'"
      :placings="state.placings"
      :slots="slots"
    />
  </div>
</template>

<style scoped>
.race-hud {
  position: absolute;
  inset: 0;
  pointer-events: none;
  font-family: system-ui, -apple-system, sans-serif;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.panel {
  position: absolute;
  background: rgba(0, 0, 0, 0.65);
  border-radius: 12px;
  padding: 20px 28px;
  backdrop-filter: blur(4px);
}

.panel--lobby {
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  min-width: 480px;
  text-align: center;
}
.panel--lobby h2 { margin: 0 0 8px; font-size: 24px; }
.panel--lobby p { margin: 0 0 16px; opacity: 0.9; }

.slot-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.slot-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  transition: background 0.2s;
}
.slot-list li.joined { background: rgba(60, 180, 90, 0.35); }
.slot-keys { display: flex; align-items: center; gap: 6px; }
.slot-key {
  font-weight: 700;
  font-size: 14px;
  padding: 3px 10px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  min-width: 36px;
  text-align: center;
}
.slot-key--sprint { background: rgba(120, 200, 255, 0.25); font-size: 12px; }
.slot-sep { opacity: 0.6; font-size: 13px; }
.slot-name { flex: 1; font-weight: 600; }
.slot-status { opacity: 0.85; font-size: 13px; }
.keys-hint {
  margin: 10px 0 0;
  font-size: 12px;
  opacity: 0.65;
  letter-spacing: 0.3em;
  text-transform: uppercase;
}

.panel--countdown {
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0, 0, 0, 0.4);
  padding: 24px 60px;
  text-align: center;
}
.countdown-number { font-size: 140px; font-weight: 900; line-height: 1; }
.countdown-hint { margin: 6px 0 0; font-size: 15px; opacity: 0.85; }
</style>
