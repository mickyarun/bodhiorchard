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
 * ExteriorScene — Dynamic village with double-row streets.
 *
 * Uses VillageLayout to compute house positions, then builds:
 *   1. Houses (Kenney procedural for tier 0/1, KayKit GLBs for tier 2/3)
 *   2. Sand-strip roads along each street + driveways
 *   3. Square fence around the village
 *   4. Name labels above each house
 *
 * Configurable member count — rebuild() destroys everything and re-lays out.
 */
import * as pc from 'playcanvas'
import { BuildingFactory } from '../buildings/BuildingFactory'
import type { AssetLoader } from '../assets/AssetLoader'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { getHouseTier } from '../buildings/HouseTierConfig'
import { WALL_HEIGHT } from '../buildings/HouseBuilder'
import {
  HOUSE_DOOR_LOCAL,
  WALL_COLLISION,
  INTERIOR_COLLISION_TIER_1,
} from './SceneConfig'
import type { PhysicsWorld } from '../physics'
import { createNameLabel } from '../characters/NameLabel'
import { RectangularFence } from '../world/RectangularFence'
import { SandRoadBuilder } from '../world/SandRoadBuilder'
import {
  computeVillageLayout,
  type VillagePlacement,
  type VillageLayoutResult,
} from '@shared/world/VillageLayout'
import type { Zone } from '@shared/world/zones'

const GROUND_COLOR = { r: 0.45, g: 0.65, b: 0.35 }

// ─── Mock member generation ───────────────────────

const MOCK_NAMES = [
  'Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank', 'Grace', 'Hank',
  'Iris', 'Jake', 'Kira', 'Leo', 'Maya', 'Nate', 'Olivia', 'Pete',
  'Quinn', 'Rosa', 'Sam', 'Tina', 'Uma', 'Vic', 'Wendy', 'Xavier',
]
const TIER_WEIGHTS = [1, 1, 1, 1, 2, 2, 3] // Mostly huts, some cottages, rare mansions

function generateMockMembers(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    user_id: `mock_${i}`,
    name: MOCK_NAMES[i % MOCK_NAMES.length] + (i >= MOCK_NAMES.length ? ` ${Math.floor(i / MOCK_NAMES.length) + 1}` : ''),
    house_level: TIER_WEIGHTS[i % TIER_WEIGHTS.length],
  }))
}

// ─── ExteriorScene ────────────────────────────────

export class ExteriorScene {
  private loader: AssetLoader
  private materials: MaterialFactory | null
  private factory: BuildingFactory
  private roads: SandRoadBuilder

  /** Current layout result — used by housetest index for door lookups. */
  layout: VillageLayoutResult | null = null

  constructor(loader: AssetLoader, materials?: MaterialFactory) {
    this.loader = loader
    this.materials = materials ?? null
    this.factory = new BuildingFactory(loader, materials)
    this.roads = new SandRoadBuilder(loader)
  }

  async build(root: pc.Entity, physics: PhysicsWorld, memberCount = 5): Promise<void> {
    const members = generateMockMembers(memberCount)
    // Housetest renders in isolation at origin with no village yaw; synthesise
    // a minimal zone so computeVillageLayout has the shape it expects.
    const testZone: Zone = { name: 'housetest', tier: 'habitation', x: 0, z: 0, radius: 14 }
    const layout = computeVillageLayout(members, testZone)
    this.layout = layout

    // Ground — sized to fit the square fence
    const b = layout.fenceBounds
    const groundSize = (b.maxX - b.minX) + 10
    this.buildGround(root, physics, groundSize, layout.center)

    // Roads (sand strips + stones + driveways)
    await this.roads.init()
    this.roads.buildRoads(root, layout.streets, layout.placements, { driveways: true })

    // Houses
    for (const p of layout.placements) {
      const tier = p.tier as 0 | 1 | 2 | 3
      if (tier <= 1) {
        await this.buildKenneyHouse(root, p, physics)
      } else {
        await this.buildKayKitHouse(root, p, physics)
      }
    }

    // Fence — square around the village
    if (this.materials) {
      const fence = new RectangularFence(this.materials)
      fence.build(root, {
        bounds: layout.fenceBounds,
        gateSide: 'south',
      })
    }
  }

  // ─── Ground ─────────────────────────────────────

  private buildGround(root: pc.Entity, physics: PhysicsWorld, size: number, center: { x: number; z: number }): void {
    const ground = new pc.Entity('Ground')
    ground.addComponent('render', { type: 'plane' })
    const mat = this.materials?.getColor(
      'housetest_ground', GROUND_COLOR.r, GROUND_COLOR.g, GROUND_COLOR.b,
    ) ?? (() => {
      const m = new pc.StandardMaterial()
      m.diffuse.set(GROUND_COLOR.r, GROUND_COLOR.g, GROUND_COLOR.b)
      m.update()
      return m
    })()
    ground.render!.meshInstances[0].material = mat
    ground.setLocalScale(size, 1, size)
    ground.setLocalPosition(center.x, -0.005, center.z)
    root.addChild(ground)
    physics.addGround(-0.05, size)
  }

  // ─── Kenney Procedural House (tier 0/1) ─────────

  private async buildKenneyHouse(
    root: pc.Entity,
    placement: VillagePlacement,
    physics: PhysicsWorld,
  ): Promise<void> {
    const tierDef = getHouseTier(placement.tier)
    const houseWidth = tierDef.width
    const houseDepth = tierDef.depth

    // Pivot entity pattern: pivot at placement position, mesh offset so
    // house center is at pivot origin. Rotation always around center.
    const pivot = new pc.Entity(`House_${placement.memberId}`)
    pivot.setPosition(placement.x, 0, placement.z)
    pivot.setLocalEulerAngles(0, placement.yawDeg, 0)
    root.addChild(pivot)

    const mesh = new pc.Entity('Mesh')
    mesh.setLocalPosition(-houseWidth / 2, 0, -houseDepth / 2)
    pivot.addChild(mesh)

    await this.factory.createFloor(mesh, houseWidth, houseDepth)
    await this.factory.createWalls(mesh, houseWidth, houseDepth, [
      { side: 'front', index: 1, type: 'door' },
    ])
    this.factory.createRoof(mesh, houseWidth, houseDepth, WALL_HEIGHT)

    // Name label at pivot center (billboard)
    const label = createNameLabel(placement.memberName, this.loader.app.graphicsDevice, WALL_HEIGHT + 0.4)
    label.setLocalPosition(0, 0, 0)
    pivot.addChild(label)

    // Physics — transform collision boxes from mesh-local to world space
    const yawRad = placement.yawDeg * Math.PI / 180
    const cos = Math.cos(yawRad)
    const sin = Math.sin(yawRad)
    // Use wall-only collision for exterior (not interior furniture colliders)
    const collisionBoxes = placement.tier === 1 ? INTERIOR_COLLISION_TIER_1 : WALL_COLLISION

    for (const box of collisionBoxes) {
      const cx = (box.minX + box.maxX) / 2
      const cz = (box.minZ + box.maxZ) / 2
      const hw = (box.maxX - box.minX) / 2
      const hd = (box.maxZ - box.minZ) / 2

      const localX = -houseWidth / 2 + cx
      const localZ = -houseDepth / 2 + cz

      const wx = placement.x + localX * cos + localZ * sin
      const wz = placement.z - localX * sin + localZ * cos

      const absC = Math.abs(cos)
      const absS = Math.abs(sin)
      physics.addStaticBox(wx, WALL_HEIGHT / 2, wz, hw * absC + hd * absS, WALL_HEIGHT / 2, hw * absS + hd * absC)
    }

    // Door collider at front wall center in pivot-local space
    const doorLocalX = -houseWidth / 2 + HOUSE_DOOR_LOCAL.x
    const doorLocalZ = -houseDepth / 2 + houseDepth
    const doorWx = placement.x + doorLocalX * cos + doorLocalZ * sin
    const doorWz = placement.z - doorLocalX * sin + doorLocalZ * cos
    physics.addDoor(
      placement.memberId, doorWx, WALL_HEIGHT / 2, doorWz,
      0.45, WALL_HEIGHT / 2, 0.05,
    )
  }

  // ─── KayKit House (tier 2/3) ────────────────────

  private async buildKayKitHouse(
    root: pc.Entity,
    placement: VillagePlacement,
    physics: PhysicsWorld,
  ): Promise<void> {
    const tierDef = getHouseTier(placement.tier)
    if (!tierDef.exteriorGlb || !tierDef.exteriorFootprint) return

    const s = tierDef.exteriorScale ?? 1.0
    const { w, d } = tierDef.exteriorFootprint

    const asset = await this.loader.load(tierDef.exteriorGlb)
    const building = this.loader.instance(asset)
    building.name = `House_${placement.memberId}`
    building.setPosition(placement.x, 0, placement.z)
    building.setLocalEulerAngles(0, placement.yawDeg, 0)
    building.setLocalScale(s, s, s)
    root.addChild(building)

    // Name label above building (billboard)
    const labelY = w * s + 0.3
    const label = createNameLabel(placement.memberName, this.loader.app.graphicsDevice, labelY)
    label.setLocalPosition(placement.x, 0, placement.z)
    root.addChild(label)

    // Physics: simple box collider matching scaled footprint
    physics.addStaticBox(
      placement.x, WALL_HEIGHT / 2, placement.z,
      (w * s) / 2, WALL_HEIGHT / 2, (d * s) / 2,
    )

    // Door at the front of the building
    const yawRad = placement.yawDeg * Math.PI / 180
    const doorLocalZ = (d * s) / 2 + 0.3
    const doorWx = placement.x + doorLocalZ * Math.sin(yawRad)
    const doorWz = placement.z + doorLocalZ * Math.cos(yawRad)
    physics.addDoor(
      placement.memberId, doorWx, WALL_HEIGHT / 2, doorWz,
      0.45, WALL_HEIGHT / 2, 0.05,
    )
  }
}
