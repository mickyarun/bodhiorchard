/**
 * TakeoverAnimGraph — Extended animation state graph for player takeover mode.
 *
 * Extends the base LOCOMOTION_STATE_GRAPH (Idle/Walk/Sit) with Sprint and Jump
 * states. Loads additional GLBs on demand and swaps the graph on the character
 * entity when entering/exiting takeover.
 *
 * Parameters:
 *   speed   (int)  — 0=idle, 1=walk, 2=sprint
 *   jumping (bool) — true triggers Jump state
 *   sitting (bool) — true triggers Sit state
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { getAnimationGLB } from '../characters/KayKitManifest'
import {
  type ContainerWithAnims,
  findAnimTrack,
  LOCOMOTION_STATE_GRAPH,
} from '../characters/AnimUtils'

// ─── Extended State Graph ─────────────────────

export const TAKEOVER_STATE_GRAPH = {
  layers: [{
    name: 'locomotion',
    states: [
      { name: 'START' },
      { name: 'Idle',   speed: 1.0 },
      { name: 'Walk',   speed: 1.0 },
      { name: 'Sprint', speed: 1.0 },
      { name: 'Jump',   speed: 1.0, loop: false },
      { name: 'Sit',    speed: 1.0 },
      { name: 'Wave',   speed: 1.0 },
      { name: 'Cheer',  speed: 1.0 },
    ],
    transitions: [
      { from: 'START', to: 'Idle', time: 0, priority: 0 },
      // Idle ↔ Walk
      {
        from: 'Idle', to: 'Walk', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_GREATER_THAN, value: 0 }],
      },
      {
        from: 'Walk', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_LESS_THAN_EQUAL_TO, value: 0 }],
      },
      // Walk ↔ Sprint
      {
        from: 'Walk', to: 'Sprint', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_GREATER_THAN, value: 1 }],
      },
      {
        from: 'Sprint', to: 'Walk', time: 0.2, priority: 0,
        conditions: [
          { parameterName: 'speed', predicate: pc.ANIM_LESS_THAN_EQUAL_TO, value: 1 },
          { parameterName: 'speed', predicate: pc.ANIM_GREATER_THAN, value: 0 },
        ],
      },
      {
        from: 'Sprint', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_LESS_THAN_EQUAL_TO, value: 0 }],
      },
      // Jump (from any movement state, priority 1 to override walk/sprint)
      {
        from: 'Idle', to: 'Jump', time: 0.1, priority: 1,
        conditions: [{ parameterName: 'jumping', predicate: pc.ANIM_EQUAL_TO, value: true }],
      },
      {
        from: 'Walk', to: 'Jump', time: 0.1, priority: 1,
        conditions: [{ parameterName: 'jumping', predicate: pc.ANIM_EQUAL_TO, value: true }],
      },
      {
        from: 'Sprint', to: 'Jump', time: 0.1, priority: 1,
        conditions: [{ parameterName: 'jumping', predicate: pc.ANIM_EQUAL_TO, value: true }],
      },
      {
        from: 'Jump', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'jumping', predicate: pc.ANIM_EQUAL_TO, value: false }],
      },
      // Sit
      {
        from: 'Idle', to: 'Sit', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'sitting', predicate: pc.ANIM_EQUAL_TO, value: true }],
      },
      {
        from: 'Sit', to: 'Idle', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'sitting', predicate: pc.ANIM_EQUAL_TO, value: false }],
      },
      // Emotes: Idle ↔ Wave (emote=1), Idle ↔ Cheer (emote=2)
      {
        from: 'Idle', to: 'Wave', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'emote', predicate: pc.ANIM_EQUAL_TO, value: 1 }],
      },
      {
        from: 'Wave', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'emote', predicate: pc.ANIM_EQUAL_TO, value: 0 }],
      },
      {
        from: 'Idle', to: 'Cheer', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'emote', predicate: pc.ANIM_EQUAL_TO, value: 2 }],
      },
      {
        from: 'Cheer', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'emote', predicate: pc.ANIM_EQUAL_TO, value: 0 }],
      },
    ],
  }],
  parameters: {
    speed:   { name: 'speed',   type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    jumping: { name: 'jumping', type: pc.ANIM_PARAMETER_BOOLEAN, value: false },
    sitting: { name: 'sitting', type: pc.ANIM_PARAMETER_BOOLEAN, value: false },
    emote:   { name: 'emote',   type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
  },
}

// Track names searched in GLBs (fuzzy match via findAnimTrack)
const SPRINT_KEYWORDS = ['Running', 'Sprint', 'Run']
const JUMP_KEYWORDS   = ['Jump', 'Jump_Full', 'Jump_Short']

// ─── Public API ───────────────────────────────

/**
 * Swap the character's state graph to the takeover graph and load
 * additional animation tracks (sprint, jump) on demand.
 */
export async function loadTakeoverAnimations(
  entity: pc.Entity,
  loader: AssetLoader,
): Promise<void> {
  const anim = entity.anim
  if (!anim) return

  // Load the movement_advanced GLB for sprint/jump tracks
  const advGlbPath = getAnimationGLB('movement_advanced')
  let advContainer: ContainerWithAnims | null = null
  try {
    const asset = await loader.load(advGlbPath)
    advContainer = asset.resource as ContainerWithAnims
    // Log discovered tracks for debugging
    if (advContainer?.animations) {
      const names = advContainer.animations.map(a => a.name || (a.resource as pc.AnimTrack)?.name)
      console.debug('[TakeoverAnimGraph] movement_advanced tracks:', names)
    }
  } catch (err) {
    console.warn('[TakeoverAnimGraph] Failed to load movement_advanced.glb:', err)
  }

  // Swap to the extended state graph
  anim.loadStateGraph(TAKEOVER_STATE_GRAPH)
  const layer = anim.baseLayer
  if (!layer) return

  // Re-assign the core 3 tracks (already loaded in memory by AssetLoader cache)
  await assignCoreAnimations(entity, loader, layer)

  // Assign sprint track from movement_advanced
  if (advContainer) {
    const sprintTrack = findTrackByKeywords(advContainer, SPRINT_KEYWORDS)
    if (sprintTrack) {
      layer.assignAnimation('Sprint', sprintTrack)
    } else {
      // Fallback: use Walk at higher playback speed
      const walkTrack = findTrackByKeywords(advContainer, ['Walking', 'Walk'])
      if (walkTrack) layer.assignAnimation('Sprint', walkTrack)
      console.debug('[TakeoverAnimGraph] No sprint track found, using walk fallback')
    }

    const jumpTrack = findTrackByKeywords(advContainer, JUMP_KEYWORDS)
    if (jumpTrack) {
      layer.assignAnimation('Jump', jumpTrack)
    } else {
      console.debug('[TakeoverAnimGraph] No jump track found, jump will use idle')
    }
  }
}

/**
 * Restore the character's original 3-state locomotion graph.
 * Called when exiting takeover mode.
 */
export async function restoreLocomotionAnimations(
  entity: pc.Entity,
  loader: AssetLoader,
): Promise<void> {
  const anim = entity.anim
  if (!anim) return

  anim.loadStateGraph(LOCOMOTION_STATE_GRAPH)
  const layer = anim.baseLayer
  if (!layer) return

  await assignCoreAnimations(entity, loader, layer)
}

// ─── Helpers ──────────────────────────────────

/** Try multiple keywords against a container until one matches. */
function findTrackByKeywords(
  container: ContainerWithAnims,
  keywords: string[],
): pc.AnimTrack | null {
  for (const kw of keywords) {
    const track = findAnimTrack(container, kw)
    if (track) return track
  }
  return null
}

/** Assign Idle/Walk/Sit tracks from the already-loaded core GLBs. */
async function assignCoreAnimations(
  _entity: pc.Entity,
  loader: AssetLoader,
  layer: pc.AnimComponentLayer,
): Promise<void> {
  const coreGlbs = [
    { path: getAnimationGLB('general'),        state: 'Idle',  keywords: ['Idle'] },
    { path: getAnimationGLB('movement_basic'), state: 'Walk',  keywords: ['Walking', 'Walk'] },
    { path: getAnimationGLB('simulation'),     state: 'Sit',   keywords: ['Sit_Chair_Idle', 'Sit'] },
    { path: getAnimationGLB('simulation'),     state: 'Wave',  keywords: ['Waving'] },
    { path: getAnimationGLB('simulation'),     state: 'Cheer', keywords: ['Cheering'] },
  ]

  for (const { path, state, keywords } of coreGlbs) {
    try {
      const asset = await loader.load(path) // cached — instant if already loaded
      const container = asset.resource as ContainerWithAnims
      const track = findTrackByKeywords(container, keywords)
      if (track) layer.assignAnimation(state, track)
    } catch {
      console.warn(`[TakeoverAnimGraph] Failed to reload ${state} track from ${path}`)
    }
  }
}
