// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
 * States: START → Idle ↔ Walk ↔ Sit ↔ Interact ↔ UseItem
 * Parameters: speed (int), sitting (bool), working (int: 0=none, 1=interact, 2=use-item)
 *
 * The "working" integer drives two tree-activity animations:
 *   1 → Interact (Kenney: interact-right, KayKit: Interact) — reaching/watering
 *   2 → UseItem  (Kenney: typing,          KayKit: Use_Item) — coding/working
 *   0 → exit back to Idle
 */
export const LOCOMOTION_STATE_GRAPH = {
  layers: [{
    name: 'locomotion',
    states: [
      { name: 'START' },
      { name: 'Idle', speed: 1.0 },
      { name: 'Walk', speed: 1.0 },
      { name: 'Sit', speed: 1.0 },
      { name: 'Interact', speed: 1.0 },
      { name: 'UseItem', speed: 1.0 },
      { name: 'Wave', speed: 1.0 },
      { name: 'Cheer', speed: 1.0 },
      { name: 'Defeat', speed: 0.6 },   // slowed down so the dejected pose reads as "resigned"
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
      // Tree-activity: Idle → Interact (working=1)
      {
        from: 'Idle', to: 'Interact', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'working', predicate: pc.ANIM_EQUAL_TO, value: 1 }],
      },
      {
        from: 'Interact', to: 'Idle', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'working', predicate: pc.ANIM_EQUAL_TO, value: 0 }],
      },
      // Tree-activity: Idle → UseItem (working=2)
      {
        from: 'Idle', to: 'UseItem', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'working', predicate: pc.ANIM_EQUAL_TO, value: 2 }],
      },
      {
        from: 'UseItem', to: 'Idle', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'working', predicate: pc.ANIM_EQUAL_TO, value: 0 }],
      },
      // Emotes: Idle → Wave (emote=1), Idle → Cheer (emote=2)
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
      // Loss emote — the avatar plays a "fallen over" animation as a
      // dejected pose. Used on the race results podium for non-winners.
      {
        from: 'Idle', to: 'Defeat', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'emote', predicate: pc.ANIM_EQUAL_TO, value: 3 }],
      },
      {
        from: 'Defeat', to: 'Idle', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'emote', predicate: pc.ANIM_EQUAL_TO, value: 0 }],
      },
    ],
  }],
  parameters: {
    speed: { name: 'speed', type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    sitting: { name: 'sitting', type: pc.ANIM_PARAMETER_BOOLEAN, value: false },
    working: { name: 'working', type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    emote: { name: 'emote', type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
  },
}
