/**
 * AnimUtils — Shared animation utilities for character factories.
 *
 * Contains the container type extension (PlayCanvas doesn't type animations),
 * animation track finder, and the shared locomotion state graph definition.
 */
import * as pc from 'playcanvas'

// ─── Container Type ────────────────────────────

/** Container.animations exists at runtime but is missing from TS declarations. */
export interface ContainerWithAnims extends pc.ContainerResource {
  animations: pc.Asset[]
}

// ─── Track Finder ──────────────────────────────

/**
 * Find an animation track by name in a container's animations.
 *
 * Tries exact match first (for KayKit tracks with precise names like "Idle_A"),
 * then falls back to case-insensitive substring match (for legacy Kenney tracks).
 */
export function findAnimTrack(
  container: ContainerWithAnims,
  keyword: string,
): pc.AnimTrack | null {
  // Exact match first
  for (const animAsset of container.animations) {
    const track = animAsset.resource as pc.AnimTrack | null
    if (track?.name === keyword) return track
  }

  // Fuzzy substring match (case-insensitive)
  const lower = keyword.toLowerCase()
  for (const animAsset of container.animations) {
    if (animAsset.name.toLowerCase().includes(lower)) {
      return animAsset.resource as pc.AnimTrack
    }
    const track = animAsset.resource as pc.AnimTrack | null
    if (track?.name?.toLowerCase().includes(lower)) {
      return track
    }
  }
  return null
}

// ─── Shared State Graph ────────────────────────

/**
 * Locomotion state graph shared by both KayKit and legacy character factories.
 *
 * States: START → Idle ↔ Walk ↔ Sit
 * Parameters: speed (int), sitting (bool)
 */
export const LOCOMOTION_STATE_GRAPH = {
  layers: [{
    name: 'locomotion',
    states: [
      { name: 'START' },
      { name: 'Idle', speed: 1.0 },
      { name: 'Walk', speed: 1.0 },
      { name: 'Sit', speed: 1.0 },
    ],
    transitions: [
      { from: 'START', to: 'Idle', time: 0, priority: 0 },
      {
        from: 'Idle', to: 'Walk', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_GREATER_THAN, value: 0 }],
      },
      {
        from: 'Walk', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_LESS_THAN_EQUAL_TO, value: 0 }],
      },
      {
        from: 'Idle', to: 'Sit', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'sitting', predicate: pc.ANIM_EQUAL_TO, value: true }],
      },
      {
        from: 'Sit', to: 'Idle', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'sitting', predicate: pc.ANIM_EQUAL_TO, value: false }],
      },
    ],
  }],
  parameters: {
    speed: { name: 'speed', type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    sitting: { name: 'sitting', type: pc.ANIM_PARAMETER_BOOLEAN, value: false },
  },
}
