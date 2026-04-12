/**
 * CharacterFactory — Creates character entities from Kenney Blocky Character GLBs.
 *
 * Each character GLB contains 27 embedded animations (idle, walk, sit, etc.).
 * The factory:
 *   1. Loads the GLB container asset
 *   2. Calls instantiateRenderEntity() (NEVER clone — skinning bug #3393)
 *   3. Attaches AnimComponent with a locomotion state graph
 *   4. Assigns animation tracks from the container
 *
 * PlayCanvas pattern: anim component on wrapper entity, render entity as child.
 * The AnimComponent auto-discovers skinned meshes in children.
 *
 * Animation activation: activate=true is passed to addComponent so that
 * loadStateGraph() starts the state machine immediately. The actual animation
 * ticking begins once the entity is added to the scene graph via addChild().
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { getCharacterGLB, CHARACTER_COUNT } from '../assets/AssetManifest'
import { hashString } from '../utils/MathUtils'
import { createNameLabel } from './NameLabel'
import { type ContainerWithAnims, findAnimTrack, LOCOMOTION_STATE_GRAPH } from './AnimUtils'

// ─── Character model known constants ─────────────
//
// Kenney Blocky Characters model-space AABB (all 6 meshes):
//   X: [-4.0, 4.0]   (width: 8.0, centered at origin)
//   Y: [-1.0, 8.0]   (height: 9.0, feet slightly below origin)
//   Z: [-4.0, 4.0]   (depth: 8.0, centered at origin)

/** Model-space height (Y extent across all meshes). */
const CHARACTER_NATIVE_HEIGHT = 9.0

/** Desired world-space height — fits under house roof (WALL_HEIGHT=1.29). */
const CHARACTER_TARGET_HEIGHT = 1.1

/** Uniform scale applied to the render entity. */
const CHARACTER_SCALE = CHARACTER_TARGET_HEIGHT / CHARACTER_NATIVE_HEIGHT

/**
 * Y offset for the render entity — the model's feet are at Y=-1 in model space.
 * After scaling, shift up so feet sit on the ground plane (Y=0).
 * offset = -yMin * scale = -(-1) * scale = 1 * scale
 */
const CHARACTER_Y_OFFSET = 1.0 * CHARACTER_SCALE

// State graph and animation utilities imported from shared modules (AnimUtils.ts)

/** Height of the name label above the character's head (in world units). */
const LABEL_HEIGHT = CHARACTER_TARGET_HEIGHT + 0.25

export interface CharacterEntity {
  entity: pc.Entity
  memberId: string
  memberName: string
}

export class CharacterFactory {
  private loader: AssetLoader
  private containerCache = new Map<string, ContainerWithAnims>()

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  /** Determine which character model variant a member gets. */
  static getVariant(userId: string, override: string | null): string {
    if (override) return override
    const variants = 'abcdefghijklmnopqr'
    return variants[hashString(userId) % CHARACTER_COUNT]
  }

  /**
   * Create a character entity with animation and name label.
   *
   * @param sitting - If true, sets the sitting parameter so the state graph
   *   transitions from Idle to Sit on the first tick after entering the scene.
   */
  async create(
    memberId: string,
    memberName: string,
    variant: string,
    x: number,
    y: number,
    z: number,
    yaw = 0,
    sitting = false,
  ): Promise<CharacterEntity> {
    const glbPath = getCharacterGLB(variant)

    // Load and cache the container
    let container = this.containerCache.get(glbPath)
    if (!container) {
      const asset = await this.loader.load(glbPath)
      container = asset.resource as ContainerWithAnims
      this.containerCache.set(glbPath, container)
    }

    // Create wrapper entity (holds anim component + label)
    const wrapper = new pc.Entity(`Character_${memberName}`)
    wrapper.setPosition(x, y, z)
    if (yaw !== 0) wrapper.setEulerAngles(0, yaw, 0)

    // Instance render entity (NEVER clone — PlayCanvas skinning bug #3393)
    //
    // Y offset depends on pose:
    //   STANDING: CHARACTER_Y_OFFSET lifts feet from model Y=-1 to ground (Y=0).
    //   SITTING:  localY=0 so the animation root (model Y=0) maps directly to
    //             wrapper.Y = seatY → character's pelvis aligns with the chair
    //             seat surface. CHARACTER_Y_OFFSET would push it 0.111 too high.
    const renderEntity = container.instantiateRenderEntity()
    renderEntity.setLocalScale(CHARACTER_SCALE, CHARACTER_SCALE, CHARACTER_SCALE)
    renderEntity.setLocalPosition(0, sitting ? 0 : CHARACTER_Y_OFFSET, 0)
    wrapper.addChild(renderEntity)

    // Add anim component — activate=true so loadStateGraph starts the state machine.
    // Animation ticking begins once the entity enters the scene graph via addChild().
    wrapper.addComponent('anim', { activate: true })

    // Load state graph and assign tracks before the entity enters the scene
    wrapper.anim!.loadStateGraph(LOCOMOTION_STATE_GRAPH)
    const layer = wrapper.anim!.baseLayer

    const idleTrack = findAnimTrack(container, 'idle')
    const walkTrack = findAnimTrack(container, 'walk')
    const sitTrack = findAnimTrack(container, 'sit')
    const interactTrack = findAnimTrack(container, 'interact-right')
    const useItemTrack = findAnimTrack(container, 'typing')

    if (layer) {
      if (idleTrack) layer.assignAnimation('Idle', idleTrack)
      if (walkTrack) layer.assignAnimation('Walk', walkTrack)
      if (sitTrack) layer.assignAnimation('Sit', sitTrack)
      if (interactTrack) layer.assignAnimation('Interact', interactTrack)
      if (useItemTrack) layer.assignAnimation('UseItem', useItemTrack)
    }

    // Set sitting parameter — state graph evaluates Idle→Sit on first tick
    if (sitting) {
      wrapper.anim!.setBoolean('sitting', true)
    }

    // Name label billboard above character head
    const label = createNameLabel(
      memberName,
      this.loader.app.graphicsDevice,
      LABEL_HEIGHT,
    )
    wrapper.addChild(label)

    return { entity: wrapper, memberId, memberName }
  }

  /** Clear cached containers (call on scene teardown). */
  clear(): void {
    this.containerCache.clear()
  }
}
