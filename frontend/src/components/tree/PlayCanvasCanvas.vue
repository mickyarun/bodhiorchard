<template>
  <div
    ref="containerRef"
    class="playcanvas-canvas"
  >
    <div
      v-if="initError"
      class="playcanvas-canvas__error"
    >
      {{ initError }}
    </div>
    <div
      v-if="tooltipText"
      class="playcanvas-canvas__tooltip"
      :style="{ left: tooltipPos.x + 'px', top: tooltipPos.y + 'px' }"
    >
      {{ tooltipText }}
    </div>
    <TouchControls
      v-if="isTouch && touchContext"
      :context="touchContext"
      :proximity-target-id="nearbyMemberId"
    />
    <!-- Garden-mode entry for touch devices — keyboard users press T
         (DashboardView), iPad users have no keys so they need a button.
         Uses pointerup which fires reliably for both mouse and touch
         on iOS Safari; @click alone can be swallowed when PlayCanvas's
         canvas-level touch listeners consume the gesture. -->
    <div
      v-if="isTouch && sceneState === 'garden'"
      class="playcanvas-canvas__take-control-wrap"
    >
      <button
        type="button"
        class="playcanvas-canvas__take-control"
        :class="{ 'playcanvas-canvas__take-control--flash': tapFlash }"
        aria-label="Take control of your character"
        @pointerup.stop="onTakeControlTap"
      >
        <span class="playcanvas-canvas__take-control-icon" aria-hidden="true">
          <svg viewBox="0 0 16 16" width="11" height="11" fill="currentColor">
            <path d="M4 2.5v11l10-5.5-10-5.5z" />
          </svg>
        </span>
        <span class="playcanvas-canvas__take-control-label">Take control</span>
      </button>
      <div
        v-if="takeoverFailureReason"
        class="playcanvas-canvas__take-control-reason"
      >
        {{ takeoverFailureReason }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { TreeData } from '@/types/dashboard'
import { GardenEngine } from '@/engine/index'
import type { EngineData, RepoHealth, ThreatSeverity, BUDStatus, RelType, SceneState } from '@/engine/types'
import { useAuthStore } from '@/stores/auth'
import { useXPStore } from '@/stores/xp'
import api from '@/services/api'
import TouchControls, { type TouchContext } from '@/components/touch/TouchControls.vue'
import { useTouchDevice } from '@/composables/useTouchDevice'

const authStore = useAuthStore()


const props = defineProps<{
  treeData: TreeData
}>()

const emit = defineEmits<{
  (e: 'scene-ready'): void
  (e: 'tree-click', info: { repoName: string }): void
  (e: 'developer-click', info: { name: string; modelName: string }): void
  (e: 'house-click', info: { name: string }): void
  (e: 'zone-enter', zone: string): void
  (e: 'zone-exit', zone: string): void
  (e: 'invite-to-race', info: { userId: string; name: string }): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const tooltipText = ref<string | null>(null)
const tooltipPos = ref({ x: 0, y: 0 })

// Touch overlay state — gated on device capability + current scene mode.
// sceneState is mirrored into a ref via the onSceneStateChange callback so
// the template reacts to engine transitions. nearbyMemberId is polled from
// the engine because proximity updates every frame and we don't want the
// churn of firing a callback at 60 Hz.
const { isTouch } = useTouchDevice()
const sceneState = ref<SceneState>('garden')
const nearbyMemberId = ref<string | null>(null)

const touchContext = computed<TouchContext | null>(() => {
  if (sceneState.value === 'takeover') return 'garden-takeover'
  if (sceneState.value === 'interior' || sceneState.value === 'coffeebar' || sceneState.value === 'cafeteria') return 'interior'
  return null
})

let proximityTimer: ReturnType<typeof setInterval> | null = null

let engine: GardenEngine | null = null
// Set to true only after `initEngine` completes — guards the auth watcher
// from firing a stale `tryConnectOrgRoom` while setData is still building
// the scene (race that produced the "CharacterSystem not ready" warning).
let engineReady = false
let resizeObserver: ResizeObserver | null = null
let resizeTimer: ReturnType<typeof setTimeout> | null = null

/**
 * Adapt TreeData (app type) to EngineData (engine type).
 * This adapter is the only place app types touch engine types.
 */
function adaptTreeData(data: TreeData): EngineData {
  return {
    repos: data.repos.map(r => ({
      repo_name: r.repo_name,
      repo_path: r.repo_path,
      branches: r.branches.map(b => ({
        name: b.name,
        file_count: b.file_count,
        commit_count: b.commit_count,
        health: b.health as RepoHealth,
        bug_count: b.bug_count,
        leaves: b.leaves.map(l => ({
          path: l.path,
          age_days: l.age_days,
          color: l.color,
          branch_name: l.branch_name,
          has_bug: l.has_bug,
        })),
      })),
      total_files: r.total_files,
      total_commits: r.total_commits,
      health: r.health as RepoHealth,
      growth_stage: r.growth_stage,
    })),
    features: data.features.map(f => ({
      title: f.title,
      status: f.status,
      source_ref: f.source_ref,
      branch_name: f.branch_name,
      repo_name: f.repo_name,
      from_bud: f.from_bud,
      linked_repos: f.linked_repos ?? [],
      code_locations: f.code_locations ?? null,
    })),
    buds: data.buds.map(b => ({
      bud_number: b.bud_number,
      title: b.title,
      status: b.status as BUDStatus,
      branch_name: b.branch_name,
      repo_name: b.repo_name,
    })),
    threats: data.threats.map(t => ({
      id: t.id,
      title: t.title,
      severity: t.severity as ThreatSeverity,
      module: t.module,
      branch_name: t.branch_name,
    })),
    members: data.members.map(m => ({
      user_id: m.user_id,
      name: m.name,
      email: m.email,
      avatar_url: m.avatar_url,
      care_pct: m.care_pct,
      top_modules: m.top_modules,
      character_model: m.character_model,
      presence: m.presence,
      level: m.level,
      level_name: m.level_name,
      house_level: m.house_level,
    })),
    agent_activity: data.agent_activity.map(a => ({
      agent_name: a.agent_name,
      action: a.action,
      timestamp: a.timestamp,
      status: a.status,
      skill_slug: a.skill_slug ?? '',
      repo_name: a.repo_name ?? null,
      bud_number: a.bud_number ?? null,
      session_id: a.session_id ?? null,
      event_type: a.event_type ?? '',
      task_id: a.task_id ?? null,
      bud_title: a.bud_title ?? null,
      impacted_repo_names: a.impacted_repo_names ?? [],
    })),
    relationships: (data.relationships ?? []).map(r => ({
      source_branch: r.source_branch,
      target_branch: r.target_branch,
      source_repo: r.source_repo,
      target_repo: r.target_repo,
      rel_type: r.rel_type as RelType,
      weight: r.weight,
    })),
    feature_skills: (data.feature_skills ?? []).map(s => ({
      feature_title: s.feature_title,
      developer_count: s.developer_count,
      developers: s.developers,
      top_developer_name: s.top_developer_name ?? null,
    })),
  }
}

async function initEngine(): Promise<void> {
  if (!containerRef.value) return

  // Clean up previous engine
  if (engine) {
    engine.destroy()
    engine = null
  }

  const w = containerRef.value.clientWidth || 1200
  const h = containerRef.value.clientHeight || 800

  engine = new GardenEngine()
  // Expose for console debugging: `__engine.toggleColliderDebug()`
  ;(window as unknown as { __engine?: GardenEngine }).__engine = engine
  await engine.init(containerRef.value, w, h, {
    onSceneReady: () => emit('scene-ready'),
    onTreeClick: (info) => emit('tree-click', { repoName: info.repoName }),
    onDeveloperClick: (info) => emit('developer-click', {
      name: info.name,
      modelName: info.modelName,
    }),
    onHouseClick: (info) => {
      emit('house-click', { name: info.name })
      console.debug('[PlayCanvasCanvas] house click:', info.memberId, 'authUser:', authStore.user?.id, 'match:', info.memberId === authStore.user?.id)
      // Only allow entering your own house
      if (info.memberId && info.memberId === authStore.user?.id) {
        engine?.enterHouse(info.memberId)
      }
    },
    onHover: (tip) => {
      if (tip) {
        tooltipText.value = tip.text
        tooltipPos.value = { x: tip.screenX + 12, y: tip.screenY - 20 }
      } else {
        tooltipText.value = null
      }
    },
    onZoneEnter: (zone) => emit('zone-enter', zone),
    onZoneExit: (zone) => emit('zone-exit', zone),
    onInviteToRace: (userId, name) => emit('invite-to-race', { userId, name }),
    onSceneStateChange: (state) => { sceneState.value = state },
  })

  // Seed the initial scene state so the touch overlay reacts correctly on
  // first render (before any transition has fired).
  sceneState.value = engine.getSceneState()

  // Tell engine who the authenticated user is (for identity preservation in
  // house visits and for JWT verification on Colyseus join). The auth store
  // may not be ready at mount time — a watcher below retries when it is.
  applyCurrentUser()

  // Enable server-driven mode BEFORE setData so CharacterSystem/AgentSystem
  // skip their local build paths — spawns come from OrgRoom snapshots instead.
  engine.enableServerDriven(true)

  await engine.setData(adaptTreeData(props.treeData))

  // Mark the engine as ready BEFORE the first connect attempt. This flag
  // gates the auth watcher so it never fires a stale `tryConnectOrgRoom`
  // while setData is still in-flight (the race that produced the
  // "CharacterSystem not ready" warning).
  engineReady = true

  // Connect to the Colyseus OrgRoom (if auth is already available). The
  // watcher on authStore.user handles the case where auth resolves later.
  await tryConnectOrgRoom()

  // Fetch XP profile to get vehicle unlocks for the engine
  const xpStore = useXPStore()
  await xpStore.fetchProfile()
  if (xpStore.profile) {
    engine.setVehicleUnlocks(xpStore.profile.vehicle_unlocks)
  }
}

/** Push the auth store's user into the engine (if available). */
function applyCurrentUser(): void {
  if (!engine) return
  if (authStore.user) {
    // Read the token directly from localStorage rather than authStore.token.
    // The axios response interceptor writes new tokens to localStorage on
    // 401-refresh but does NOT update the Pinia ref, so authStore.token can
    // be stale (old expired JWT) while localStorage holds the fresh one.
    // Using localStorage ensures Colyseus receives the latest token and
    // onAuth's verifyUserToken doesn't reject with "invalid auth token".
    const freshToken = localStorage.getItem('bodhiorchard_token') ?? authStore.token ?? null
    engine.setCurrentUser({
      id: authStore.user.id,
      name: authStore.user.name,
      characterModel: authStore.user.character_model,
      token: freshToken,
    })
  } else {
    engine.setCurrentUser(null)
  }
}

/** Connect to the Colyseus OrgRoom if both auth and org_id are ready. */
async function tryConnectOrgRoom(): Promise<void> {
  if (!engine || !authStore.user || !props.treeData.org_id) return

  // Colyseus WebSocket joins bypass the axios 401 interceptor, so an expired
  // JWT causes "invalid auth token" with no automatic refresh. A lightweight
  // axios call forces the interceptor to refresh the token if needed — then
  // applyCurrentUser reads the fresh token from localStorage.
  try {
    await api.get('/v1/auth/me')
  } catch {
    // Refresh failed — interceptor will redirect to login if unrecoverable.
    return
  }

  // Re-apply auth state so the engine gets the (possibly just-refreshed) token.
  applyCurrentUser()
  try {
    await engine.connectToOrgRoom(props.treeData.org_id)
  } catch (err) {
    console.warn('[PlayCanvasCanvas] OrgRoom connect failed:', err)
  }
}

function onResize(): void {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (!engine || !containerRef.value) return
    const w = containerRef.value.clientWidth
    const h = containerRef.value.clientHeight
    engine.resize(w, h)
  }, 200)
}

const initError = ref<string | null>(null)

onMounted(async () => {
  try {
    await initEngine()
  } catch (err) {
    console.error('[PlayCanvasCanvas] Failed to initialize 3D engine:', err)
    initError.value = 'Failed to load 3D scene. Please refresh the page.'
  }

  if (containerRef.value) {
    resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(containerRef.value)
  }

  // Poll proximity target at 10 Hz — only used to dim/brighten the touch
  // Greet (3) and Invite (4) buttons. Polling instead of a per-frame
  // callback keeps the engine loop free of UI churn.
  proximityTimer = setInterval(() => {
    nearbyMemberId.value = engine?.getNearbyMemberId() ?? null
  }, 100)
})

watch(
  () => props.treeData,
  async () => {
    if (engine) {
      try {
        await engine.setData(adaptTreeData(props.treeData))
      } catch (err) {
        console.error('[PlayCanvasCanvas] Failed to update scene data:', err)
      }
    }
  },
  { deep: true },
)

// React to auth becoming available after mount. In practice `authStore.user`
// is often null when PlayCanvasCanvas first mounts (fetchUser is async) — in
// that case initEngine skips setCurrentUser + connectToOrgRoom, and this
// watcher kicks off the connection once auth resolves.
//
// Gated on `engineReady` so it never races with initEngine's own setData
// build — if auth resolves mid-build, the watcher defers and initEngine's
// final tryConnectOrgRoom call handles it.
watch(
  () => authStore.user,
  async (user) => {
    if (!engine || !engineReady) return
    applyCurrentUser()
    if (user) {
      await tryConnectOrgRoom()
    }
  },
)

/** Toggle relationship arc visibility. */
function toggleArcs(): boolean {
  return engine?.toggleArcs() ?? false
}

/** Exit house interior back to garden (callable from parent). */
function exitHouse(): void {
  engine?.exitHouse()
}

/** Focus camera on a repo tree (callable from parent). */
function focusOnRepo(repoName: string): void {
  engine?.focusOnRepo(repoName)
}

/** Clear camera focus back to overview (callable from parent). */
function clearFocus(): void {
  engine?.clearFocus()
}

/** Take control of your character in the garden (callable from parent). */
function takeoverCharacter(): void {
  const userId = authStore.user?.id
  if (userId) engine?.takeoverCharacter(userId)
}

/** Touch-overlay button handler. Briefly flashes the button so the
 *  user gets visible feedback that the tap was received, then calls
 *  into the engine and — if the engine silently bails — surfaces
 *  the reason inline via `takeoverFailureReason`. iPad has no easy
 *  console access, so this is how users see what went wrong. */
const tapFlash = ref(false)
const takeoverFailureReason = ref<string | null>(null)

function onTakeControlTap(): void {
  tapFlash.value = true
  setTimeout(() => { tapFlash.value = false }, 180)
  takeoverFailureReason.value = null

  const userId = authStore.user?.id
  if (import.meta.env.DEV) {
    console.log('[TakeControl] tap', {
      userId,
      hasEngine: !!engine,
      sceneState: sceneState.value,
    })
  }
  if (!userId) {
    takeoverFailureReason.value = 'Not signed in.'
    return
  }
  if (!engine) {
    takeoverFailureReason.value = 'Engine still loading — try again in a moment.'
    return
  }
  Promise.resolve(engine.takeoverCharacter(userId))
    .then(() => {
      // If sceneState didn't flip, the engine set a bail reason we
      // can surface. Success clears the message automatically since
      // the whole button hides (v-if on sceneState === 'garden').
      if (engine && sceneState.value === 'garden') {
        takeoverFailureReason.value = engine.takeoverBailReason
          ?? 'Take control did nothing — engine state may be stuck.'
      }
    })
    .catch(err => {
      console.error('[TakeControl] takeoverCharacter threw', err)
      takeoverFailureReason.value = `Error: ${(err as Error)?.message ?? err}`
    })
}

/** Exit takeover mode back to overview (callable from parent). */
function exitTakeover(): void {
  engine?.exitTakeover()
}

/** Whether engine is in takeover mode. */
function isTakeover(): boolean {
  return engine?.isTakeover ?? false
}

/** Whether the player is actively controlling a character (takeover OR interior). */
function isInControl(): boolean {
  return engine?.isInControl ?? false
}

defineExpose({ toggleArcs, exitHouse, focusOnRepo, clearFocus, takeoverCharacter, exitTakeover, isTakeover, isInControl })

onUnmounted(() => {
  engineReady = false
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (resizeTimer) {
    clearTimeout(resizeTimer)
  }
  if (proximityTimer) {
    clearInterval(proximityTimer)
    proximityTimer = null
  }
  if (engine) {
    engine.destroy()
    engine = null
  }
})
</script>

<style scoped>
.playcanvas-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 400px;
}

.playcanvas-canvas :deep(canvas) {
  display: block;
}

.playcanvas-canvas__error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #ef5350;
  font-size: 14px;
  text-align: center;
  z-index: 10;
}

.playcanvas-canvas__tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  white-space: pre-line;
  z-index: 10;
  max-width: 250px;
}

/* Position wrapper so the button + inline error stack vertically
   and stay centred. The wrapper is just for layout — all the
   game-button styling lives on the button itself. */
.playcanvas-canvas__take-control-wrap {
  position: absolute;
  left: 50%;
  bottom: max(88px, calc(env(safe-area-inset-bottom) + 72px));
  transform: translateX(-50%);
  z-index: 60;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  pointer-events: none; /* children flip this on */
}

.playcanvas-canvas__take-control-reason {
  pointer-events: auto;
  max-width: 280px;
  padding: 6px 12px;
  border-radius: 10px;
  background: rgba(15, 20, 30, 0.85);
  color: #ffd764;
  font-size: 12px;
  text-align: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4),
              0 0 0 1px rgba(212, 168, 67, 0.5);
}

/* Compact warm-amber action button. The theme's secondary
   (#D4A843) reads as gold against the green garden — far more
   contrast than primary-on-primary. Sized to feel like a pill
   UI button, not a dominating call-to-action. */
.playcanvas-canvas__take-control {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 18px 10px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(
    180deg,
    #f2c971 0%,
    #d4a843 55%,
    #a67d26 100%
  );
  color: #2a1a00;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.3);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    inset 0 -2px 0 rgba(0, 0, 0, 0.18),
    0 3px 0 #6b4e12,
    0 6px 14px rgba(0, 0, 0, 0.5),
    0 0 0 1.5px rgba(40, 24, 0, 0.7);
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  pointer-events: auto;
  cursor: pointer;
  transition: transform 0.08s ease, box-shadow 0.08s ease,
    filter 0.15s ease, background 0.15s ease;
}

.playcanvas-canvas__take-control:hover {
  filter: brightness(1.06);
}

.playcanvas-canvas__take-control:active,
.playcanvas-canvas__take-control--flash {
  transform: translateY(2px);
  background: linear-gradient(
    180deg,
    #ffe79f 0%,
    #f5d27a 55%,
    #c09536 100%
  );
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.35),
    inset 0 -1px 0 rgba(0, 0, 0, 0.22),
    0 1px 0 #6b4e12,
    0 2px 6px rgba(0, 0, 0, 0.4),
    0 0 0 1.5px rgba(40, 24, 0, 0.7),
    0 0 16px rgba(255, 208, 110, 0.55);
}

.playcanvas-canvas__take-control-icon {
  display: inline-flex;
  width: 18px;
  height: 18px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #2a1a00;
  color: #ffd764;
  box-shadow:
    inset 0 1px 1px rgba(255, 255, 255, 0.15),
    0 0 0 1px rgba(255, 255, 255, 0.4);
}

.playcanvas-canvas__take-control-icon svg {
  margin-left: 1px; /* optical center the play triangle */
}

.playcanvas-canvas__take-control-label {
  line-height: 1;
}

</style>
