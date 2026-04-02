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
import { ZoneSign } from '../world/ZoneSign'
import { SkySystem } from '../environment/SkySystem'
import { GroundSystem } from '../environment/GroundSystem'
import { CloudSystem } from '../environment/CloudSystem'
import { PineTreeSystem } from '../environment/PineTreeSystem'
import { BushSystem } from '../environment/BushSystem'
import { ForestLake } from '../environment/ForestLake'
import { MountainBackdrop } from '../environment/MountainBackdrop'
import { CoffeeBarBuilder } from '../buildings/CoffeeBarBuilder'
import { CafeteriaBuilder } from '../buildings/CafeteriaBuilder'
import { HousingVillage } from '../buildings/HousingVillage'
import { StandupPavilion } from '../buildings/StandupPavilion'
import { PoolResortBuilder } from '../buildings/PoolResortBuilder'
import { BuildingFactory } from '../buildings/BuildingFactory'
import type { HouseResult } from '../buildings/HouseBuilder'
import { CharacterSystem } from '../characters/CharacterSystem'
import { GardenBirdSystem } from '../world/GardenBirdSystem'
import { GardenAnimalSystem } from '../world/GardenAnimalSystem'
import { LanternSystem } from '../effects/LanternSystem'
import { CircularFence } from '../world/CircularFence'
import { AgentCharacterSystem } from '../agents'

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
  private characterSystem: CharacterSystem | null = null
  private gardenBirds: GardenBirdSystem | null = null
  private gardenAnimals: GardenAnimalSystem | null = null
  private lanterns: LanternSystem | null = null
  private agentSystem: AgentCharacterSystem | null = null
  private signEntities: pc.Entity[] = []

  // Building entities (for destruction)
  private buildingEntities: pc.Entity[] = []

  // Shared data for Phase 3+
  private _memberHouseMap = new Map<string, HouseResult>()

  // Garden world root — toggled off during interior mode
  private _gardenRoot: pc.Entity | null = null

  constructor(app: Application, materials: MaterialFactory) {
    this.app = app
    this.materials = materials
    this.loader = new AssetLoader(app.app)
    this.layout = new WorldLayout()
  }

  /** Build the entire world from engine data. */
  async build(data: EngineData): Promise<void> {
    const currentBuild = ++this.buildId

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
    if (this.buildId !== currentBuild) return

    // 2. Environment (independent of data)
    this.sky = new SkySystem()
    this.sky.build(this.app, this.materials)

    this.ground = new GroundSystem()
    this.ground.build(this.app, this.materials)
    this.ground.addZoneOverlays(this.app, this.layout.getAllZones())

    this.clouds = new CloudSystem()
    this.clouds.build(this.app, this.materials)

    // 3. Repo visualization (default: trees with decoration)
    this.repoVis = this.createRepoVisualization()
    const treeZones = await this.repoVis.build(this.app, data, this.layout)
    if (this.buildId !== currentBuild) return
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
    if (this.buildId !== currentBuild) return

    // 4. Buildings
    const buildingFactory = new BuildingFactory(this.loader, this.materials)

    const coffeeZone = this.layout.getZone('coffee_bar')
    const cafeteriaZone = this.layout.getZone('cafeteria')
    const poolZone = this.layout.getZone('pool')
    const pavilionZone = this.layout.getZone('pavilion')

    if (coffeeZone) {
      const coffeeBuilder = new CoffeeBarBuilder(buildingFactory)
      const coffeeResult = await coffeeBuilder.build(this.app, coffeeZone.x, coffeeZone.z)
      if (this.buildId !== currentBuild) return
      this.buildingEntities.push(coffeeResult.entity)
      this.layout.addExclusionZones([coffeeResult.exclusionZone])
      this.layout.registerSeats(coffeeResult.seats)
    }

    if (cafeteriaZone) {
      const cafeteriaBuilder = new CafeteriaBuilder(buildingFactory)
      const cafeteriaResult = await cafeteriaBuilder.build(this.app, cafeteriaZone.x, cafeteriaZone.z)
      if (this.buildId !== currentBuild) return
      this.buildingEntities.push(cafeteriaResult.entity)
      this.layout.addExclusionZones([cafeteriaResult.exclusionZone])
      this.layout.registerSeats(cafeteriaResult.seats)
    }

    // Housing village
    if (data.members.length > 0) {
      const village = new HousingVillage(this.loader)
      const housingResult = await village.build(this.app, data.members, this.layout)
      if (this.buildId !== currentBuild) return
      this.buildingEntities.push(housingResult.entity)
      this.layout.addExclusionZones([housingResult.exclusionZone])
      this.layout.registerSeats(housingResult.seats)
      this._memberHouseMap = housingResult.memberHouseMap
    }

    if (poolZone) {
      const poolBuilder = new PoolResortBuilder(buildingFactory, this.loader)
      const poolResult = await poolBuilder.build(this.app, poolZone.x, poolZone.z)
      if (this.buildId !== currentBuild) return
      this.buildingEntities.push(poolResult.entity)
      this.layout.addExclusionZones([poolResult.exclusionZone])
      this.layout.registerSeats(poolResult.seats)
    }

    if (pavilionZone) {
      const pavilion = new StandupPavilion(buildingFactory)
      const pavilionResult = await pavilion.build(this.app, pavilionZone.x, pavilionZone.z)
      if (this.buildId !== currentBuild) return
      this.buildingEntities.push(pavilionResult.entity)
      this.layout.addExclusionZones([pavilionResult.exclusionZone])
      this.layout.registerSeats(pavilionResult.seats)
    }

    // 4b. Characters (after all buildings → seats and houses are registered)
    if (data.members.length > 0) {
      try {
        this.characterSystem = new CharacterSystem(this.loader)
        await this.characterSystem.build(
          this.app,
          data.members,
          this._memberHouseMap,
          [...this.layout.getSeats()],
        )
        // Wire tree position lookup for dev activity character movement
        this.characterSystem.setTreePositionLookup(
          (repoName) => this.getTreePosition(repoName),
        )
      } catch (err) {
        console.warn('[SceneManager] Character loading failed (scene continues):', err)
        this.characterSystem = null
      }
      if (this.buildId !== currentBuild) return
    }

    // 5. Paths between zones + zone signs
    const zones = this.layout.getAllZones()
    const pathRoutes = PathSystem.defaultRoutes([...zones])
    this.paths = new PathSystem()
    await this.paths.build(this.app, this.loader, pathRoutes)
    if (this.buildId !== currentBuild) return

    // Zone signs at each building zone entrance (facing orchard)
    for (const zone of zones) {
      if (zone.name === 'orchard') continue // no sign for center
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
    if (this.buildId !== currentBuild) return

    this.bushes = new BushSystem()
    await this.bushes.build(this.app, this.loader, this.layout.getExclusionZones(), pathRoutes)
    if (this.buildId !== currentBuild) return

    // 6b. Forest lake — pond inside a dense forest cluster, opposite the mountains (SE)
    // Positioned at the far edge of the world, like mountains
    const FOREST_LAKE_X = 180
    const FOREST_LAKE_Z = -160
    this.forestLake = new ForestLake()
    await this.forestLake.build(this.app, this.loader, FOREST_LAKE_X, FOREST_LAKE_Z)
    if (this.buildId !== currentBuild) return

    // 6c. Mountain backdrop — Eastern Ghats-style range at the far edge
    this.mountains = new MountainBackdrop()
    await this.mountains.build(this.app, this.loader)
    if (this.buildId !== currentBuild) return

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

    // 8b. Ambient effects — lanterns along paths
    this.lanterns = new LanternSystem(this.app.app)
    this.lanterns.buildAlongRoutes(PathSystem.defaultRoutes([...zones]))

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
    if (this.buildId !== currentBuild) return

    // 9. Wrap all garden content under a single root for scene transitions.
    // When entering a house interior, gardenRoot.enabled = false hides the entire garden.
    // Camera and lights are kept outside so they work in both modes.
    this.wrapGardenRoot()

  }

  /** Per-frame update for animated subsystems. */
  update(dt: number): void {
    this.sky?.update(dt)
    this.clouds?.update(dt)
    this.forestLake?.update(dt)
    this.repoVis?.update?.(dt)
    this.gardenBirds?.update(dt)
    this.gardenAnimals?.update(dt)
    this.agentSystem?.update(dt)
    this.characterSystem?.update(dt)
  }

  /** Rebuild entire scene with new data. */
  async rebuild(data: EngineData): Promise<void> {
    this.teardown()
    await this.build(data)
  }

  // ─── Public Accessors ─────────────────────────

  get repoVisualization(): RepoVisualization | null { return this.repoVis }
  get arcsRef(): RelationshipArcs | null { return this.arcs }
  get memberHouseMap(): Map<string, HouseResult> { return this._memberHouseMap }
  get characterSystemRef(): CharacterSystem | null { return this.characterSystem }
  get worldLayout(): WorldLayout { return this.layout }
  get gardenRootEntity(): pc.Entity | null { return this._gardenRoot }
  get agentSystemRef(): AgentCharacterSystem | null { return this.agentSystem }

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

  private buildZoneFences(factory: BuildingFactory): void {
    if (!factory.materialFactory) return
    const fence = new CircularFence(factory.materialFactory)

    // ── Zone property fences (solid) ──────────────────────────────────────────
    // Zones to skip entirely (no fence).
    const noFence = new Set(['orchard', 'pool'])
    // Per-zone radius overrides — use zone.radius when not listed.
    const radiusOverride: Record<string, number> = {
      housing: 18,   // wider ring to encompass the full village spread
    }

    for (const zone of this.layout.getAllZones()) {
      if (noFence.has(zone.name)) continue

      const radius    = radiusOverride[zone.name] ?? zone.radius
      const gateAngle = Math.atan2(-zone.x, -zone.z)
      this.buildingEntities.push(fence.build(this.app.root, {
        radius,
        cx:        zone.x,
        cz:        zone.z,
        gateAngle,
        gateWidth: 3.0,
        style:     'solid',
      }))
    }

    // ── Outer campus perimeter (light rail) ────────────────────────────────────
    // worldRadius is the furthest zone edge from origin (~51 units).
    // +8 gives a comfortable visual margin before the green ground fades out.
    const outerRadius = this.layout.getWorldRadius() + 8
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

    this.pines?.destroy()
    this.pines = null

    for (const sign of this.signEntities) {
      sign.destroy()
    }
    this.signEntities = []

    this.paths?.destroy()
    this.paths = null

    this.characterSystem?.destroy()
    this.characterSystem = null

    for (const entity of this.buildingEntities) {
      entity.destroy()
    }
    this.buildingEntities = []
    this._memberHouseMap.clear()

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

    this.layout.reset()
  }

  destroy(): void {
    this.teardown()
    this.loader.clear()
  }
}
