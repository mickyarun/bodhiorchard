// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * SceneManager — THE orchestrator that builds the entire world.
 *
 * Build order (dependency-driven):
 *   1. Load all needed GLBs via AssetLoader.loadBatch() (single batch)
 *   2. Build environment: sky, ground (independent of data)
 *   3. Build procedural trees from data.repos via ProceduralTreeSystem
 *   4. Build buildings (coffee bar, cafeteria, village, pool, pavilion)
 *   4b. Place characters at seats/houses (needs building seats + house map)
 *   5. Build paths between zones + zone signs
 *   6. Scatter pine trees + bushes (after buildings, so exclusion zones exist)
 *   7. Build relationship arcs
 *   8. Add effects (string lights)
 *
 * Wired into GardenEngine.setData().
 */
import * as pc from 'playcanvas'
import type { Application } from './Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { EngineData } from '../types'
import { AssetLoader } from '../assets/AssetLoader'
import {
  getAllDecorationGLBs,
  getEnvironmentGLBs, getBuildingGLBs, getMiscGLBs,
  AGENT_ROBOT,
  AGENT_SPACESHIP,
} from '../assets/AssetManifest'
import { WorldLayout } from '../world/WorldLayout'
import type { RepoVisualization } from '../world/RepoVisualization'
import { ProceduralTreeSystem } from '../world/ProceduralTreeSystem'
import { RelationshipArcs } from '../world/RelationshipArcs'
import { PathSystem } from '../world/PathSystem'
import { buildRoutes } from '@shared/world/paths'
import { ZoneSign } from '../world/ZoneSign'
import { SkySystem } from '../environment/SkySystem'
import { GroundSystem } from '../environment/GroundSystem'
import { CloudSystem } from '../environment/CloudSystem'
import { PineTreeSystem } from '../environment/PineTreeSystem'
import { BushSystem } from '../environment/BushSystem'
import { ForestLake } from '../environment/ForestLake'
import { MountainBackdrop } from '../environment/MountainBackdrop'
import { HubAnchor } from '../world/HubAnchor'
import { GrassDressing } from '../world/GrassDressing'
import { DecorativePropScatter } from '../world/DecorativePropScatter'
import { CoffeeBarBuilder } from '../buildings/CoffeeBarBuilder'
import { CafeteriaBuilder } from '../buildings/CafeteriaBuilder'
import { HousingVillage } from '../buildings/HousingVillage'
import { HousingState } from '../buildings/HousingState'
import { StandupPavilion } from '../buildings/StandupPavilion'
import { PoolResortBuilder } from '../buildings/PoolResortBuilder'
import type { WaterSurface } from '../effects/WaterSurface'
import { BuildingFactory } from '../buildings/BuildingFactory'
import type { HouseResult } from '../buildings/HouseBuilder'
import { CharacterSystem } from '../characters/CharacterSystem'
import { GardenBirdSystem } from '../world/GardenBirdSystem'
import { GardenAnimalSystem } from '../world/GardenAnimalSystem'
import { LanternSystem } from '../effects/LanternSystem'
import { CircularFence } from '../world/CircularFence'
import { AgentCharacterSystem } from '../agents'
import { PhysicsWorld } from '../physics'
import {
  TakeoverPhysicsBuilder,
  type HutInfo,
  type PondObstacle,
} from '../takeover/TakeoverPhysicsBuilder'
import { GATE_WIDTH } from '../world/FenceConstants'

export class SceneManager {
  private app: Application
  private materials: MaterialFactory
  private loader: AssetLoader
  private layout: WorldLayout

  // Build guard — prevents concurrent builds from racing
  private buildId = 0

  // Subsystems (reverse destroy order)
  private sky: SkySystem | null = null
  private ground: GroundSystem | null = null
  private clouds: CloudSystem | null = null
  private repoVis: RepoVisualization | null = null
  private arcs: RelationshipArcs | null = null
  private pines: PineTreeSystem | null = null
  private bushes: BushSystem | null = null
  private forestLake: ForestLake | null = null
  private mountains: MountainBackdrop | null = null
  private paths: PathSystem | null = null
  private grassDressing: GrassDressing | null = null
  private decorProps: DecorativePropScatter | null = null
  private characterSystem: CharacterSystem | null = null
  private gardenBirds: GardenBirdSystem | null = null
  private gardenAnimals: GardenAnimalSystem | null = null
  private lanterns: LanternSystem | null = null
  private agentSystem: AgentCharacterSystem | null = null
  private signEntities: pc.Entity[] = []

  // Building entities (for destruction)
  private buildingEntities: pc.Entity[] = []

  /** Zones that have NO fence (orchard = hub, pool = own collider, housing = RectangularFence). */
  private readonly ZONES_WITHOUT_FENCES = new Set(['orchard', 'pool', 'housing'])

  // Takeover physics (created async, null if Rapier WASM fails to load)
  private _physics: PhysicsWorld | null = null
  /**
   * Kept alive for the lifetime of the physics world so its `houseBodies`
   * tracking persists across tier upgrades. Recreated per `initPhysics` run.
   */
  private _takeoverPhysicsBuilder: TakeoverPhysicsBuilder | null = null
  private buildingHuts: HutInfo[] = []
  private pondObstacle: PondObstacle | null = null
  private bodhiTrunk: { x: number; z: number; radius: number; topY: number } | null = null
  private poolWater: WaterSurface | null = null

  // Shared data for Phase 3+
  private _memberHouseMap = new Map<string, HouseResult>()
  private _housing = new HousingState()

  /** Member lookup by user_id — includes character_model for identity preservation when visiting houses. */
  private _memberDataMap = new Map<string, { user_id: string; name: string; character_model: string | null }>()

  // Garden world root — toggled off during interior mode
  private _gardenRoot: pc.Entity | null = null

  constructor(app: Application, materials: MaterialFactory) {
    this.app = app
    this.materials = materials
    this.loader = new AssetLoader(app.app)
    this.layout = new WorldLayout()
  }

  /**
   * Build the entire world from engine data.
   *
   * @param data   The scene data to build.
   * @param signal Optional AbortSignal. When aborted at any await checkpoint,
   *               the build exits via `throw signal.reason` (a DOMException
   *               with name='AbortError' by default). The internal `buildId`
   *               cancellation continues to work as a defense-in-depth fallback
   *               for callers that don't pass a signal.
   */
  async build(data: EngineData, signal?: AbortSignal): Promise<void> {
    const currentBuild = ++this.buildId
    /** Throws if build was either superseded (buildId) or externally aborted (signal). */
    const checkCancelled = (): boolean => {
      if (signal?.aborted) {
        // Web Platform convention: throwIfAborted() throws signal.reason
        signal.throwIfAborted()
      }
      return this.buildId !== currentBuild
    }

    // Tune the world to this org's repo count. Must run before any
    // zone-positioned entity is built — the orchard radius drives both
    // tree placement and the perimeter belt offset. WorldLayout boots
    // at baseline in its ctor; rescale brings it to the real N.
    this.layout.rescale(data.repos.length)

    // Cache member data for identity lookups (character_model for house visits)
    this._memberDataMap.clear()
    for (const m of data.members) {
      this._memberDataMap.set(m.user_id, {
        user_id: m.user_id,
        name: m.name,
        character_model: m.character_model,
      })
    }

    // 1. Batch preload all GLBs (trees are now procedural — no tree GLBs needed)
    const allPaths = [
      ...getAllDecorationGLBs(),
      ...getEnvironmentGLBs(),
      ...getBuildingGLBs(),
      ...getMiscGLBs(),
      AGENT_ROBOT,
      AGENT_SPACESHIP,
      // Character GLBs loaded on-demand by CharacterFactory (not batch — isolated error handling)
    ]
    const uniquePaths = [...new Set(allPaths)]
    await this.loader.loadBatch(uniquePaths)

    // Check if a newer build was started while we were loading
    if (checkCancelled()) return

    // 2. Environment (independent of data)
    this.sky = new SkySystem()
    this.sky.build(this.app, this.materials)

    this.ground = new GroundSystem()
    this.ground.build(this.app, this.materials)
    this.ground.addZoneOverlays(this.app, this.layout.getAllZones())

    this.clouds = new CloudSystem()
    this.clouds.build(this.app, this.materials)

    // 2b. HubAnchor — orchard-center landmark (Bodhi tree + mound + plaza).
    // Built BEFORE repo trees so its exclusion zone is registered in time
    // and so it anchors the scene before anything else populates the hub.
    const buildingFactory = new BuildingFactory(this.loader, this.materials)
    const hubAnchor = new HubAnchor(buildingFactory, this.layout.getHubGeometry())
    const hubResult = await hubAnchor.build(this.app, 0, 0)
    if (checkCancelled()) return
    this.buildingEntities.push(hubResult.entity)
    this.layout.addExclusionZones([hubResult.exclusionZone])
    this.bodhiTrunk = hubResult.trunkCollider

    // 3. Repo visualization (default: trees with decoration)
    this.repoVis = this.createRepoVisualization()
    const treeZones = await this.repoVis.build(this.app, data, this.layout)
    if (checkCancelled()) return
    this.layout.addExclusionZones(treeZones)

    // 3b. Garden birds — roam between repo trees
    this.gardenBirds = new GardenBirdSystem(this.app.app)
    await this.gardenBirds.init(this.loader)
    if (this.repoVis instanceof ProceduralTreeSystem) {
      this.gardenBirds.setTrees(this.repoVis.getTreeMap())
    }

    // 3c. Garden animals — cube-pets wandering on the ground
    this.gardenAnimals = new GardenAnimalSystem(this.app.app)
    await this.gardenAnimals.init(this.loader)
    if (checkCancelled()) return

    // 4. Buildings (buildingFactory created above in phase 2b for HubAnchor)
    const coffeeZone = this.layout.getZone('coffee_bar')
    const cafeteriaZone = this.layout.getZone('cafeteria')
    const poolZone = this.layout.getZone('pool')
    const pavilionZone = this.layout.getZone('pavilion')

    if (coffeeZone) {
      const coffeeBuilder = new CoffeeBarBuilder(buildingFactory)
      const coffeeResult = await coffeeBuilder.build(this.app, coffeeZone.x, coffeeZone.z)
      if (checkCancelled()) return
      this.buildingEntities.push(coffeeResult.entity)
      this.layout.addExclusionZones([coffeeResult.exclusionZone])
      this.layout.registerSeats(coffeeResult.seats)
      // Coffee-bar hut is offset inside its root so it centers on the zone
      // rather than spilling into one quadrant. Physics colliders must use
      // the hut's actual world origin (hutWorldOrigin), not the zone center,
      // or walls misalign from the visual by HUT_OFFSET_{X,Z}.
      this.buildingHuts.push({
        x: coffeeResult.hutWorldOrigin.x,
        z: coffeeResult.hutWorldOrigin.z,
        yawDeg: coffeeResult.entity.getEulerAngles().y,
        ...coffeeResult.hutDims,
      })
    }

    if (cafeteriaZone) {
      const cafeteriaBuilder = new CafeteriaBuilder(buildingFactory)
      const cafeteriaResult = await cafeteriaBuilder.build(this.app, cafeteriaZone.x, cafeteriaZone.z)
      if (checkCancelled()) return
      this.buildingEntities.push(cafeteriaResult.entity)
      this.layout.addExclusionZones([cafeteriaResult.exclusionZone])
      this.layout.registerSeats(cafeteriaResult.seats)
      this.buildingHuts.push({
        x: cafeteriaZone.x, z: cafeteriaZone.z,
        yawDeg: cafeteriaResult.entity.getEulerAngles().y,
        ...cafeteriaResult.hutDims,
      })
    }

    // Housing village (builds its own fence + roads + driveways)
    if (data.members.length > 0) {
      const village = new HousingVillage(this.loader)
      const housingResult = await village.build(this.app, data.members, this.layout, this.materials)
      if (checkCancelled()) return
      this.buildingEntities.push(housingResult.entity)
      this.layout.addExclusionZones([housingResult.exclusionZone])
      this.layout.registerSeats(housingResult.seats)
      this._memberHouseMap = housingResult.memberHouseMap
      this._housing.absorb(village, housingResult)
    }

    if (poolZone) {
      const poolBuilder = new PoolResortBuilder(buildingFactory, this.loader)
      const poolResult = await poolBuilder.build(this.app, poolZone.x, poolZone.z)
      if (checkCancelled()) return
      this.buildingEntities.push(poolResult.entity)
      this.layout.addExclusionZones([poolResult.exclusionZone])
      this.layout.registerSeats(poolResult.seats)
      this.pondObstacle = poolResult.pondObstacle
      this.poolWater = poolResult.waterSurface
    }

    if (pavilionZone) {
      const pavilion = new StandupPavilion(buildingFactory)
      const pavilionResult = await pavilion.build(this.app, pavilionZone.x, pavilionZone.z)
      if (checkCancelled()) return
      this.buildingEntities.push(pavilionResult.entity)
      this.layout.addExclusionZones([pavilionResult.exclusionZone])
      this.layout.registerSeats(pavilionResult.seats)
      // Open-air standup area has no walls → no physics hut to register.
      if (pavilionResult.hutDims) {
        this.buildingHuts.push({
          x: pavilionZone.x, z: pavilionZone.z,
          yawDeg: pavilionResult.entity.getEulerAngles().y,
          ...pavilionResult.hutDims,
        })
      }
    }

    // 4b. Characters — CharacterSystem is a renderer only; entities are
    // spawned on demand from OrgRoom state by GardenEngine.connectToOrgRoom.
    try {
      this.characterSystem = new CharacterSystem(this.loader)
      this.characterSystem.build(this.app)
    } catch (err) {
      console.warn('[SceneManager] CharacterSystem init failed (scene continues):', err)
      this.characterSystem = null
    }
    if (checkCancelled()) return

    // 4c. Initialize Rapier physics for takeover mode (non-blocking)
    await this.initPhysics(currentBuild, signal)
    if (checkCancelled()) return

    // 5. Paths between zones + zone signs
    const zones = this.layout.getAllZones()
    // Housing: route to the gate entrance (world-space, accounts for village rotation)
    const pathZones = zones.map(z => {
      if (z.name === 'housing' && this._housing.gatePosition) {
        return { ...z, ...this._housing.gatePosition }
      }
      return z
    })
    const pathRoutes = buildRoutes(pathZones)
    this.paths = new PathSystem()
    await this.paths.build(this.app, this.loader, pathRoutes)
    if (checkCancelled()) return

    // 5b. Grass dressing — macro tint overlay + path-wear halos. Uses the
    // routes we just computed. Rendered at y=0.005..0.012 so it sits
    // beneath path strips (y=0.015) and zone overlays (y=0.02).
    this.grassDressing = new GrassDressing()
    this.grassDressing.build(this.app, pathRoutes)

    // Zone signs at each building zone entrance (facing orchard)
    for (const zone of zones) {
      if (zone.name === 'orchard') continue // no sign for center
      if (zone.name === 'coffee_bar') continue // the COFFEE awning is its label
      if (zone.name === 'cafeteria') continue // the CAFETERIA awning is its label
      // Place sign at edge of zone, facing inward
      const dx = -zone.x
      const dz = -zone.z
      const dist = Math.sqrt(dx * dx + dz * dz)
      const nx = dx / (dist || 1)
      const nz = dz / (dist || 1)
      const signX = zone.x + nx * (zone.radius * 0.7)
      const signZ = zone.z + nz * (zone.radius * 0.7)
      const sign = ZoneSign.create(this.app.app, zone.name, signX, signZ)
      this.app.root.addChild(sign)
      this.signEntities.push(sign)
    }

    // 6. Scatter pine trees + bushes (after all exclusion zones are registered)
    this.pines = new PineTreeSystem()
    await this.pines.build(this.app, this.loader, this.layout.getExclusionZones())
    if (checkCancelled()) return

    this.bushes = new BushSystem()
    await this.bushes.build(this.app, this.loader, this.layout.getExclusionZones(), pathRoutes)
    if (checkCancelled()) return

    // 6a. Decorative prop scatter — flower patches + rock piles in mid-distance
    // wedges, complementing BushSystem's single bushes/stumps.
    this.decorProps = new DecorativePropScatter()
    await this.decorProps.build(
      this.app, this.loader, this.layout.getExclusionZones(), pathRoutes,
    )
    if (checkCancelled()) return

    // 6b. Forest lake — pond inside a dense forest cluster, opposite the mountains (SE)
    // Positioned at the far edge of the world, like mountains
    const FOREST_LAKE_X = 180
    const FOREST_LAKE_Z = -160
    this.forestLake = new ForestLake()
    await this.forestLake.build(this.app, this.loader, FOREST_LAKE_X, FOREST_LAKE_Z)
    if (checkCancelled()) return

    // 6c. Mountain backdrop — Eastern Ghats-style range at the far edge
    this.mountains = new MountainBackdrop()
    await this.mountains.build(this.app, this.loader)
    if (checkCancelled()) return

    // 7. Relationship arcs
    this.arcs = new RelationshipArcs()
    const treePositions = new Map<string, pc.Vec3>()
    for (const repo of data.repos) {
      const pos = this.repoVis.getTreePosition(repo.repo_name)
      if (pos) treePositions.set(repo.repo_name, pos)
    }
    const arcsEntity = this.arcs.build(this.materials, data.relationships, treePositions)
    this.app.root.addChild(arcsEntity)

    // 8. Effects
    // String lights are now built as part of each building's entity tree
    // (created by BuildingFactory.createStringLights in each builder)

    // 8b. Ambient effects — lanterns along paths (skip housing compound)
    this.lanterns = new LanternSystem(this.app.app)
    const housingZone = this.layout.getZone('housing')
    const lanternExclusions = housingZone
      ? [{ x: housingZone.x, z: housingZone.z, radius: housingZone.radius + 4 }]
      : []
    // Reuse the exact `pathRoutes` computed for PathSystem.build() — those
    // account for the housing gate-position swap and any future curve data.
    // Recomputing from raw `zones` would put lanterns on a different route
    // than the actual path (misaligned near the housing gate).
    this.lanterns.buildAlongRoutes(pathRoutes, lanternExclusions)

    // 8c. Zone fences — circular wooden fences around each building zone.
    // Gate angle points toward orchard (0,0) so it aligns with the path entrance.
    // Orchard is the central hub; it has paths converging from all sides so no fence.
    this.buildZoneFences(buildingFactory)

    // 8d. Agent characters — always initialized so live WebSocket events can spawn robots
    // even if no agents are active at page load time
    this.agentSystem = new AgentCharacterSystem()
    await this.agentSystem.build(
      this.app, this.loader, data.agent_activity,
      (repoName) => this.getTreePosition(repoName),
    )
    if (checkCancelled()) return

    // 9. Wrap all garden content under a single root for scene transitions.
    // When entering a house interior, gardenRoot.enabled = false hides the entire garden.
    // Camera and lights are kept outside so they work in both modes.
    this.wrapGardenRoot()

  }

  /**
   * Per-frame update for animated subsystems.
   *
   * `viewerPos` is plumbed through to `repoVis.update` so visualizations like
   * ProceduralTreeSystem can run distance-LOD against a ground-level viewer
   * (takeover mode). Other modes pass `null` and everything renders.
   */
  update(dt: number, viewerPos: pc.Vec3 | null = null): void {
    this.sky?.update(dt)
    this.clouds?.update(dt)
    this.forestLake?.update(dt)
    this.poolWater?.update(dt)
    this.repoVis?.update?.(dt, viewerPos)
    this.gardenBirds?.update(dt)
    this.gardenAnimals?.update(dt)
    this.agentSystem?.update(dt)
    // CharacterSystem transform apply happens in POST-update (see
    // CharacterSystem.build where the postUpdate listener is registered) so it
    // runs after PlayCanvas's animationUpdate phase — otherwise the anim
    // component's binding re-evaluates our setLocalRotation away and remote
    // characters slide without turning.
  }

  /**
   * Rebuild entire scene with new data.
   *
   * @param signal Optional AbortSignal forwarded to `build()`. Aborting at
   *   any await checkpoint causes the build to throw `signal.reason` (a
   *   DOMException with name='AbortError'). Used by GardenEngine's
   *   SerializedExecutor to abort in-flight builds on disposal.
   */
  async rebuild(data: EngineData, signal?: AbortSignal): Promise<void> {
    this.teardown()
    await this.build(data, signal)
  }

  // ─── Public Accessors ─────────────────────────

  get repoVisualization(): RepoVisualization | null { return this.repoVis }
  get arcsRef(): RelationshipArcs | null { return this.arcs }
  get memberHouseMap(): Map<string, HouseResult> { return this._memberHouseMap }
  get housingVillageRef(): HousingVillage | null { return this._housing.village }
  get characterSystemRef(): CharacterSystem | null { return this.characterSystem }
  get worldLayout(): WorldLayout { return this.layout }
  get gardenRootEntity(): pc.Entity | null { return this._gardenRoot }
  get agentSystemRef(): AgentCharacterSystem | null { return this.agentSystem }
  get assetLoader(): AssetLoader { return this.loader }
  get physicsWorld(): PhysicsWorld | null { return this._physics }

  /** Look up a member's character model by user_id. */
  getMemberCharacterModel(userId: string): string | null {
    return this._memberDataMap.get(userId)?.character_model ?? null
  }

  /** Look up full member data (user_id, name, character_model) by user_id. */
  getMember(userId: string): { user_id: string; name: string; character_model: string | null } | null {
    return this._memberDataMap.get(userId) ?? null
  }

  /** All pickable entities: repo trees + feature branches + houses + agents.
   *  NOT cached — tree features are added asynchronously during growth animation,
   *  and agent entities spawn/despawn at runtime. */
  getPickableEntities(): pc.Entity[] {
    const treePicks = this.repoVis?.getPickableEntities?.() ?? []
    const housePicks: pc.Entity[] = []
    for (const house of this._memberHouseMap.values()) {
      housePicks.push(house.entity)
    }
    const agentPicks = this.agentSystem?.getPickableEntities() ?? []
    return treePicks.concat(housePicks, agentPicks)
  }

  getTreePosition(repoName: string): pc.Vec3 | null {
    return this.repoVis?.getTreePosition(repoName) ?? null
  }

  toggleArcs(): boolean {
    return this.arcs?.toggle() ?? false
  }

  // ─── Zone Fences ──────────────────────────────

  /**
   * Build fences for all zones + one light rail fence around the whole campus.
   *
   * Zone fences (solid style):
   *   Gate angle = atan2(-zone.x, -zone.z) → opening faces toward the orchard hub.
   *   Gate width 3.0 units gives clearance for path stones + characters.
   *
   * Outer perimeter (rail style):
   *   Closed ring (no gate) at worldRadius + 8 units margin.
   *   Wide post spacing (~4 units) keeps entity count low for a large ring.
   */
  /**
   * Initialize Rapier physics world and register all collision bodies for takeover mode.
   * Non-blocking: if Rapier WASM fails to load, scene builds without physics and
   * takeover will log a warning when attempted.
   *
   * Concurrent-build safe: if another build started during WASM load, the freshly
   * created physics world is destroyed before return to avoid a WASM memory leak.
   */
  private async initPhysics(currentBuild: number, signal?: AbortSignal): Promise<void> {
    try {
      // Zero gravity — top-down movement, no falling
      const created = await PhysicsWorld.create({ x: 0, y: 0, z: 0 })

      // Concurrent build guard — discard orphaned world to free WASM memory.
      // Also check the external abort signal so disposal during physics init
      // doesn't leak the WASM-backed world.
      if (this.buildId !== currentBuild || signal?.aborted) {
        created.destroy()
        return
      }

      this._physics = created
      const builder = new TakeoverPhysicsBuilder(this._physics)
      builder.registerHouses(this._memberHouseMap)
      builder.registerBuildings(this.buildingHuts)
      if (this.pondObstacle) {
        builder.registerPond(this.pondObstacle)
      }
      if (this.bodhiTrunk) {
        builder.registerHubAnchor(this.bodhiTrunk)
      }
      builder.registerPerimeter(this.getOuterPerimeterRadius())
      this._housing.registerPhysicsFence(builder)
      const fencedZones = this.layout.getAllZones().filter(z => !this.ZONES_WITHOUT_FENCES.has(z.name))
      builder.registerCircularFences(fencedZones)
      // Keep the builder alive so rebuildHousePhysics can reuse its
      // per-member body tracking on tier upgrades.
      this._takeoverPhysicsBuilder = builder

      // Doors disabled until takeover starts (prevents fire on scene build)
      this._physics.setDoorsEnabled(false)
      console.debug('[SceneManager] Physics initialized:',
        this._memberHouseMap.size, 'houses,',
        this.buildingHuts.length, 'huts')
    } catch (err) {
      console.warn('[SceneManager] Physics init failed — takeover will be disabled:', err)
      this._physics = null
    }
  }

  /**
   * Rebuild just one house's physics colliders to match the current
   * `HouseResult` in `_memberHouseMap`. Call after `HousingVillage.rebuildByMemberId`
   * completes so the Rapier walls/door match the freshly-built visual tier.
   *
   * No-op when physics never initialized (WASM load failed), the builder
   * was never created, or the member has no entry in the house map.
   */
  rebuildHousePhysics(memberId: string): void {
    if (!this._physics || !this._takeoverPhysicsBuilder) return
    const house = this._memberHouseMap.get(memberId)
    if (!house) return
    this._takeoverPhysicsBuilder.removeHouse(memberId)
    this._takeoverPhysicsBuilder.registerHouse(memberId, house)
  }

  /**
   * Wrap all garden world content under a single gardenRoot entity.
   * Called at the end of build() — re-parents everything except camera/lights.
   * Enables interior mode to hide the entire garden via gardenRoot.enabled = false.
   */
  private wrapGardenRoot(): void {
    this._gardenRoot = new pc.Entity('GardenRoot')
    this.app.root.addChild(this._gardenRoot)

    // Entities to keep as direct children of EngineRoot (visible in all modes)
    const keep = new Set(['Camera', 'Sun', 'FillSky', 'GardenRoot', 'InteriorRoot'])
    const toMove: pc.Entity[] = []

    for (const child of [...this.app.root.children] as pc.Entity[]) {
      if (!keep.has(child.name)) {
        toMove.push(child)
      }
    }

    for (const child of toMove) {
      this._gardenRoot.addChild(child)
    }
  }

  /**
   * Outer perimeter radius used by BOTH the visual rail fence and the
   * Rapier physics collider. Taking the max of the static zone-derived
   * world radius and the dynamic village reach means the rail grows to
   * enclose the housing village when house count pushes its footprint
   * beyond the fixed `housing` zone radius in `shared/world/zones.ts`.
   */
  private getOuterPerimeterRadius(): number {
    return this._housing.getOuterPerimeterRadius(this.layout.getWorldRadius())
  }

  private buildZoneFences(factory: BuildingFactory): void {
    if (!factory.materialFactory) return
    const fence = new CircularFence(factory.materialFactory)

    // ── Zone property fences (solid) ──────────────────────────────────────────
    for (const zone of this.layout.getAllZones()) {
      if (this.ZONES_WITHOUT_FENCES.has(zone.name)) continue

      const radius    = zone.radius
      const gateAngle = Math.atan2(-zone.x, -zone.z)
      this.buildingEntities.push(fence.build(this.app.root, {
        radius,
        cx:        zone.x,
        cz:        zone.z,
        gateAngle,
        gateWidth: GATE_WIDTH,
        style:     'solid',
      }))
    }

    // ── Outer campus perimeter (light rail) ────────────────────────────────────
    const outerRadius = this.getOuterPerimeterRadius()
    this.buildingEntities.push(fence.build(this.app.root, {
      radius:    outerRadius,
      cx:        0,
      cz:        0,
      gateWidth: 0,        // closed ring — no gate needed at the perimeter
      style:     'rail',
    }))
  }

  // ─── Repo Visualization Factory ─────────────────

  /**
   * Create the repo visualization implementation.
   * Override this method to swap in an alternative visualization
   * (e.g. crystals, planets, buildings) without touching the rest of SceneManager.
   */
  protected createRepoVisualization(): RepoVisualization {
    return new ProceduralTreeSystem(this.materials)
  }

  // ─── Cleanup ──────────────────────────────────

  /** Tear down all subsystems in reverse creation order. */
  teardown(): void {
    this.arcs?.destroy(this.materials)
    this.arcs = null

    this.mountains?.destroy()
    this.mountains = null

    this.forestLake?.destroy()
    this.forestLake = null

    this.bushes?.destroy()
    this.bushes = null

    this.decorProps?.destroy()
    this.decorProps = null

    this.pines?.destroy()
    this.pines = null

    for (const sign of this.signEntities) {
      sign.destroy()
    }
    this.signEntities = []

    this.paths?.destroy()
    this.paths = null

    this.grassDressing?.destroy()
    this.grassDressing = null

    this.characterSystem?.destroy()
    this.characterSystem = null

    for (const entity of this.buildingEntities) {
      entity.destroy()
    }
    this.buildingEntities = []
    this._housing.reset()
    this._memberHouseMap.clear()
    this._memberDataMap.clear()

    this.agentSystem?.destroy()
    this.agentSystem = null

    this.lanterns?.destroy()
    this.lanterns = null

    this.gardenAnimals?.destroy()
    this.gardenAnimals = null

    this.gardenBirds?.destroy()
    this.gardenBirds = null

    this.repoVis?.destroy()
    this.repoVis = null

    this.clouds?.destroy()
    this.clouds = null

    this.ground?.destroy(this.materials)
    this.ground = null

    this.sky?.destroy()
    this.sky = null

    // Release materials acquired by effects
    this.materials.release('cloud')
    this.materials.release('sl_bulb')
    this.materials.release('sl_wire')
    this.materials.release('sl_pole')
    this.materials.release('umbrella_pole')
    this.materials.release('umbrella_canopy')
    this.materials.release('ground_grass')
    this.materials.release('fence_post')
    this.materials.release('fence_panel')
    this.materials.release('fence_gate')

    this._gardenRoot?.destroy()
    this._gardenRoot = null

    this._physics?.destroy()
    this._physics = null
    this._takeoverPhysicsBuilder = null
    this.buildingHuts = []
    this.pondObstacle = null
    this.bodhiTrunk = null

    this.layout.reset()
  }

  destroy(): void {
    this.teardown()
    this.loader.clear()
  }
}
