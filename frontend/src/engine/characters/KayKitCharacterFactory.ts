/**
 * KayKitCharacterFactory — Creates KayKit Adventurer character entities.
 *
 * KayKit characters differ from Kenney Blocky in several ways:
 *   1. Use real skeletal skinning (23-joint Rig_Medium)
 *   2. Animations are in separate GLB files (not embedded in character GLB)
 *   3. 7 named mesh parts (Head, Body, ArmLeft, ArmRight, LegLeft, LegRight, + accessory)
 *   4. Single shared material with a gradient atlas texture
 *
 * Color tinting: each mesh instance gets a cloned material with diffuse color
 * applied per body region (shirt→Body, pants→Legs, skin→Head+Arms).
 *
 * PlayCanvas pattern: wrapper entity with AnimComponent, render entity as child.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { CharacterConfig } from './CharacterConfig'
import type { CharacterEntity } from './CharacterFactory'
import { getCharacterDef, getCoreAnimationGLBs } from './KayKitManifest'
import { createNameLabel } from './NameLabel'
import { type ContainerWithAnims, findAnimTrack, LOCOMOTION_STATE_GRAPH } from './AnimUtils'

// ─── Model Constants (measured from GLB AABB) ──

/** KayKit characters are ~2.4 units tall (measured AABB Y: 0 to 2.398). */
const KAYKIT_NATIVE_HEIGHT = 2.4
const KAYKIT_TARGET_HEIGHT = 1.0
const KAYKIT_SCALE = KAYKIT_TARGET_HEIGHT / KAYKIT_NATIVE_HEIGHT
const KAYKIT_Y_OFFSET = 0.0
const LABEL_HEIGHT = KAYKIT_TARGET_HEIGHT + 0.25

// ─── Body Region → Mesh Name Mapping ───────────

type BodyRegion = 'shirt' | 'pants' | 'skin'

const REGION_MESH_PATTERNS: Record<BodyRegion, string[]> = {
  shirt: ['Body'],
  pants: ['LegLeft', 'LegRight'],
  skin:  ['Head', 'ArmLeft', 'ArmRight'],
}

/** Animation track names from KayKit GLBs mapped to state graph states. */
const ANIM_TRACK_MAP: Record<string, string> = {
  'Idle':  'Idle_A',
  'Walk':  'Walking_A',
  'Sit':   'Sit_Chair_Idle',
}

// ─── Hex Color Helper ──────────────────────────

function hexToColor(hex: string): pc.Color {
  const r = parseInt(hex.substring(0, 2), 16) / 255
  const g = parseInt(hex.substring(2, 4), 16) / 255
  const b = parseInt(hex.substring(4, 6), 16) / 255
  return new pc.Color(r, g, b)
}

// ─── Factory ───────────────────────────────────

export class KayKitCharacterFactory {
  private loader: AssetLoader
  private containerCache = new Map<string, ContainerWithAnims>()
  private animContainerCache = new Map<string, ContainerWithAnims>()

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  /**
   * Create a KayKit character entity with animations, color tinting, and name label.
   * @param skipLabel - If true, omit the name label (used in preview scenes).
   */
  async create(
    memberId: string,
    memberName: string,
    config: CharacterConfig,
    x: number,
    y: number,
    z: number,
    yaw = 0,
    sitting = false,
    skipLabel = false,
  ): Promise<CharacterEntity> {
    const def = getCharacterDef(config.characterId)
    if (!def) {
      throw new Error(`Unknown KayKit character: ${config.characterId}`)
    }

    const container = await this.loadContainer(def.glb)

    // Create wrapper entity (holds anim component + label)
    const wrapper = new pc.Entity(`KayKit_${memberName}`)
    wrapper.setPosition(x, y, z)
    if (yaw !== 0) wrapper.setEulerAngles(0, yaw, 0)

    // Instantiate render entity
    const renderEntity = container.instantiateRenderEntity()
    renderEntity.setLocalScale(KAYKIT_SCALE, KAYKIT_SCALE, KAYKIT_SCALE)
    renderEntity.setLocalPosition(0, sitting ? 0 : KAYKIT_Y_OFFSET, 0)
    wrapper.addChild(renderEntity)

    // Apply color tinting per body region — store cloned materials for cleanup
    const clonedMats = this.applyColorTinting(renderEntity, config)
    ;(wrapper as unknown as { _clonedMaterials: pc.StandardMaterial[] })._clonedMaterials = clonedMats

    // Set up animation component with shared locomotion state graph
    wrapper.addComponent('anim', { activate: true })
    wrapper.anim!.loadStateGraph(LOCOMOTION_STATE_GRAPH)
    await this.assignAnimations(wrapper)

    if (sitting) {
      wrapper.anim!.setBoolean('sitting', true)
    }

    // Name label billboard (shared utility) — skip in preview mode
    if (!skipLabel && memberName) {
      const label = createNameLabel(memberName, this.loader.app.graphicsDevice, LABEL_HEIGHT)
      wrapper.addChild(label)
    }

    return { entity: wrapper, memberId, memberName }
  }

  // ─── Color Tinting ─────────────────────────

  /**
   * Apply per-region color tinting to mesh instances.
   * Returns cloned materials so the caller can dispose them on cleanup.
   */
  private applyColorTinting(renderEntity: pc.Entity, config: CharacterConfig): pc.StandardMaterial[] {
    const colors: Record<BodyRegion, pc.Color> = {
      shirt: hexToColor(config.shirtColor),
      pants: hexToColor(config.pantsColor),
      skin: hexToColor(config.skinColor),
    }

    const clonedMaterials: pc.StandardMaterial[] = []
    const renderComponents = renderEntity.findComponents('render') as pc.RenderComponent[]
    for (const rc of renderComponents) {
      for (const mi of rc.meshInstances) {
        const meshName = mi.node?.name || ''
        const region = this.getRegionForMesh(meshName)
        if (!region) continue

        const mat = (mi.material as pc.StandardMaterial).clone()
        mat.diffuse = colors[region]
        mat.update()
        mi.material = mat
        clonedMaterials.push(mat)
      }
    }
    return clonedMaterials
  }

  private getRegionForMesh(meshName: string): BodyRegion | null {
    for (const [region, patterns] of Object.entries(REGION_MESH_PATTERNS)) {
      if (patterns.some(p => meshName.includes(p))) {
        return region as BodyRegion
      }
    }
    return null
  }

  // ─── Animation Loading ─────────────────────

  private async assignAnimations(wrapper: pc.Entity): Promise<void> {
    const layer = wrapper.anim!.baseLayer
    if (!layer) return

    const assigned = new Set<string>()

    for (const glbPath of getCoreAnimationGLBs()) {
      const container = await this.loadAnimContainer(glbPath)

      for (const [stateName, trackName] of Object.entries(ANIM_TRACK_MAP)) {
        if (assigned.has(stateName)) continue

        const track = findAnimTrack(container, trackName)
        if (track) {
          layer.assignAnimation(stateName, track)
          assigned.add(stateName)
        }
      }
    }
  }

  // ─── Asset Loading ─────────────────────────

  private async loadContainer(path: string): Promise<ContainerWithAnims> {
    let container = this.containerCache.get(path)
    if (!container) {
      const asset = await this.loader.load(path)
      container = asset.resource as ContainerWithAnims
      this.containerCache.set(path, container)
    }
    return container
  }

  private async loadAnimContainer(path: string): Promise<ContainerWithAnims> {
    let container = this.animContainerCache.get(path)
    if (!container) {
      const asset = await this.loader.load(path)
      container = asset.resource as ContainerWithAnims
      this.animContainerCache.set(path, container)
    }
    return container
  }

  /** Clear cached containers (call on scene teardown). */
  clear(): void {
    this.containerCache.clear()
    this.animContainerCache.clear()
  }
}
