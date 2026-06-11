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
 * RacerAvatarAnim — the animation state machine for one race avatar.
 *
 * Split out of RacerAvatar so transform/pose smoothing and anim-graph
 * driving evolve independently (and both files stay inside the module's
 * size budget). RacerAvatar owns the entity and kinematics; this class
 * owns every `wrapper.anim` interaction:
 *
 *   - Walk/Run track swapping on the KayKit locomotion graph's Walk
 *     state (sprint reads as a run, casual movement as a walk).
 *   - The velocity-driven Idle ↔ Walk/Run picker.
 *   - Knockdown (Defeat emote, Death_A fall) enter/leave edges.
 *   - The post-finish Cheer latch.
 *
 * Animation driving matches the dashboard's `CharacterSystem` pattern:
 * setInteger('speed', 0|1) to switch Idle ↔ Walk. Never touches
 * anim.speed (varying the playback multiplier caused visible "jumping"
 * because the step cycle re-keyed mid-stride).
 *
 * Does NOT own the factory's cached animation GLBs (shared, lifecycle
 * tied to the factory) — `reset()` only drops local references.
 */
import type * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { findAnimTrack, type ContainerWithAnims } from '../characters/AnimUtils'
import { getAnimationGLB } from '../characters/KayKitManifest'

/** Animation track names used by the race scene — all resolved via findAnimTrack. */
const WALK_TRACK_NAME = 'Walking_A'
const RUN_TRACK_NAME = 'Running_A'

/** Below this velocity, swap back to the Idle state. Avoids swap-thrash at rest. */
const IDLE_SWAP_THRESHOLD_MPS = 0.5

/** Above this velocity, assume the player is sprinting (swap Walk → Running_A). */
const SPRINT_SWAP_THRESHOLD_MPS = 4.0

type AnimState = 'idle' | 'walk' | 'run'

export class RacerAvatarAnim {
  private entity: pc.Entity | null = null
  private walkTrack: pc.AnimTrack | null = null
  private runTrack: pc.AnimTrack | null = null
  private currentAnimState: AnimState = 'idle'

  /**
   * Hurdle knockdown: while the server reports the racer down we hold the
   * Defeat state (Death_A — a fall-to-ground track) and ignore
   * velocity-driven anim picking; on get-up the emote clears and the
   * locomotion graph blends back through Idle into Walk.
   */
  private knockedDown = false

  /**
   * When the server marks this racer as finished, we force the anim graph
   * through Idle → Cheer (emote=2) regardless of incoming kinematics. The
   * flag also makes kinematics updates a no-op for anim-state picking so
   * a late-arriving velocity patch doesn't yank the avatar back into Walk
   * between the finish-line crossing and the UI phase change.
   */
  private finished = false

  /**
   * Resolve the Walk/Run tracks from the shared movement GLB. Throws if
   * either track is missing — the caller treats that as a build failure.
   */
  async load(loader: AssetLoader): Promise<void> {
    const movementBasicPath = getAnimationGLB('movement_basic')
    const asset = await loader.load(movementBasicPath)
    const container = asset.resource as ContainerWithAnims

    this.walkTrack = findAnimTrack(container, WALK_TRACK_NAME)
    this.runTrack = findAnimTrack(container, RUN_TRACK_NAME)
    if (!this.walkTrack) throw new Error(`RacerAvatarAnim: missing ${WALK_TRACK_NAME} in ${movementBasicPath}`)
    if (!this.runTrack) throw new Error(`RacerAvatarAnim: missing ${RUN_TRACK_NAME} in ${movementBasicPath}`)
  }

  /** Bind the wrapper entity whose `anim` component this machine drives. */
  attach(entity: pc.Entity): void {
    this.entity = entity
  }

  /**
   * Velocity-driven state update — called on every server kinematics
   * patch. Honors the finished latch and the knockdown edges before
   * falling through to the Idle/Walk/Run picker.
   */
  onKinematics(velocityMps: number, isSprinting: boolean, isKnockedDown: boolean): void {
    // After the finish line we hold the Cheer state — see `finished`.
    if (this.finished) return

    if (isKnockedDown !== this.knockedDown) {
      this.knockedDown = isKnockedDown
      this.applyKnockdownState(isKnockedDown)
    }
    // While on the ground the Defeat state owns the rig — velocity-driven
    // state picking resumes on the get-up edge above.
    if (this.knockedDown) return

    const nextState = this.pickAnimState(velocityMps, isSprinting)
    if (nextState === this.currentAnimState) return

    this.applyAnimState(nextState)
    this.currentAnimState = nextState
  }

  /**
   * Latch the finished Cheer emote (or clear it). Idempotent; calling
   * with the current value is a no-op. Returns whether the value changed
   * so the caller can keep its own edge bookkeeping.
   */
  setFinished(finished: boolean): boolean {
    if (this.finished === finished) return false
    this.finished = finished

    const anim = this.entity?.anim
    if (!anim) return true

    if (finished) {
      // Push the graph through Walk → Idle (speed=0) so the Idle → Cheer
      // edge can fire on the next tick. Cheer has no direct transition
      // from Walk in LOCOMOTION_STATE_GRAPH.
      anim.setInteger('speed', 0)
      anim.setInteger('emote', 2)
      this.currentAnimState = 'idle'
    } else {
      anim.setInteger('emote', 0)
    }
    return true
  }

  /** Drop references on avatar teardown. Tracks are factory-owned. */
  reset(): void {
    this.entity = null
    this.walkTrack = null
    this.runTrack = null
    this.currentAnimState = 'idle'
    this.knockedDown = false
    this.finished = false
  }

  /**
   * Enter / leave the fall animation. Entering pushes the graph through
   * Idle (speed=0) so the Idle → Defeat edge can fire — same trick as
   * `setFinished` uses for Cheer; Defeat's track is Death_A, a fall to
   * the ground. Leaving clears the emote, blending back up through Idle.
   */
  private applyKnockdownState(down: boolean): void {
    const anim = this.entity?.anim
    if (!anim) return
    if (down) {
      anim.setInteger('speed', 0)
      anim.setInteger('emote', 3)
      this.currentAnimState = 'idle'
    } else {
      anim.setInteger('emote', 0)
    }
  }

  private pickAnimState(velocityMps: number, isSprinting: boolean): AnimState {
    if (velocityMps < IDLE_SWAP_THRESHOLD_MPS) return 'idle'
    if (isSprinting && velocityMps >= SPRINT_SWAP_THRESHOLD_MPS) return 'run'
    return 'walk'
  }

  private applyAnimState(state: AnimState): void {
    const anim = this.entity?.anim
    if (!anim) return
    const layer = anim.baseLayer
    if (!layer) return

    if (state === 'idle') {
      anim.setInteger('speed', 0)
      return
    }

    // Swap the Walk state's track to the appropriate variant.
    const track = state === 'run' ? this.runTrack : this.walkTrack
    if (track) layer.assignAnimation('Walk', track)
    anim.setInteger('speed', 1)
  }
}
