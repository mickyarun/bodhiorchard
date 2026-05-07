// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * GardenEngine — Public API for the 3D garden visualization engine.
 *
 * This is the ONLY entry point the Vue layer uses.
 * Zero imports from @/stores, @/types, @/views.
 *
 * API:
 *   init(container, width, height, callbacks?) — boots PlayCanvas app
 *   setData(data)                              — receives engine data, builds scene
 *   resize(width, height)                      — handles viewport resize
 *   destroy()                                  — full cleanup
 *   toggleArcs()                               — toggle relationship arc visibility
 *   focusOnRepo(repoName)                      — focus camera on a tree
 *   clearFocus()                               — show all trees
 *   enterHouse(memberId)                       — enter a house interior
 *   exitHouse()                                — exit back to garden
 */
import * as pc from 'playcanvas'
import type {
  EngineData,
  EngineCallbacks,
  EngineEvents,
} from './types'
import { toWorld } from '@shared/world/geom'
import type { HouseResult } from './buildings/HouseBuilder'
import { Application } from './core/Application'
import { EventBus } from './core/EventBus'
import { InputManager } from './input/InputManager'
import { CameraController, type CameraState } from './camera/CameraController'
import { MaterialFactory } from './rendering/MaterialFactory'
import { SceneManager } from './core/SceneManager'
import { TreePickerSystem } from './interaction/TreePickerSystem'
import { InteriorManager } from './interior'
import { CoffeeBarManager } from './coffeebar'
import { COFFEE_DOOR_LOCAL_Z } from './buildings/CoffeeBarBuilder'
import { CafeteriaManager } from './cafeteria'
import { CAFETERIA_DOOR_OFFSET } from './buildings/CafeteriaBuilder'
import {
  TakeoverController,
  TakeoverCamera,
  TakeoverUI,
  ProximitySystem,
  loadTakeoverAnimations,
  restoreLocomotionAnimations,
} from './takeover'
import { drawColliderWireframes } from './physics'
import { OrgRoomClient, type MemberStateSnapshot } from '../multiplayer'
import type { CharacterSystem } from './characters/CharacterSystem'
import { SerializedExecutor } from './utils/SerializedExecutor'
import { VehicleController } from './vehicles/VehicleController'
import { VehicleSystem } from './vehicles/VehicleSystem'
import { getVehicleDef } from './vehicles/VehicleManifest'

export { type EngineData, type EngineCallbacks, type SceneState } from './types'

import type { SceneState } from './types'

/**
 * Resolve a house's exit spawn in world space. `exitPosition` is stored
 * LOCAL to the house tile (corner-origin); composition with `house.pivot`
 * yields the world-space teleport target. Falls back to pivot centre when
 * pivot is missing (un-wrapped HouseResult — shouldn't happen post-build).
 */
function exitPositionWorld(house: HouseResult): { x: number; z: number; yaw: number } {
  if (!house.pivot) {
    const p = house.entity.getPosition()
    return { x: p.x, z: p.z, yaw: house.exitPosition.yaw }
  }
  const w = toWorld(house.exitPosition, house.pivot)
  return { x: w.x, z: w.z, yaw: house.exitPosition.yaw + house.pivot.yawDeg }
}

export class GardenEngine {
  private app: Application | null = null
  private input: InputManager | null = null
  private camera: CameraController | null = null
  private materials: MaterialFactory | null = null
  private sceneManager: SceneManager | null = null
  private events: EventBus<EngineEvents>
  private canvas: HTMLCanvasElement | null = null
  private callbacks: EngineCallbacks = {}
  private picker: TreePickerSystem | null = null

  // Interior exploration
  private interior: InteriorManager | null = null
  // Coffee bar interior (shared across the org)
  private coffeeBar: CoffeeBarManager | null = null
  // Blocks the walk-through trigger during exit teleport so the player
  // doesn't instantly re-enter after being placed just outside the door.
  private _coffeeBarReentryCooldownMs = 0
  // Cafeteria interior (shared across the org)
  private cafeteria: CafeteriaManager | null = null
  private _cafeteriaReentryCooldownMs = 0
  // Backing store for sceneState. All existing code writes `this.sceneState =
  // ...`, so we expose it via a getter/setter pair — the setter fires the
  // onSceneStateChange callback whenever the state actually changes, giving
  // UI layers (e.g. the touch-control overlay) a single subscription point
  // without touching any of the ~24 assignment sites.
  private _sceneState: SceneState = 'garden'
  private get sceneState(): SceneState { return this._sceneState }
  private set sceneState(next: SceneState) {
    if (this._sceneState === next) return
    this._sceneState = next
    this.callbacks.onSceneStateChange?.(next)
  }
  private savedCameraState: CameraState | null = null
  private _interiorMemberId: string | null = null
  // Re-entrancy guard for enterHouse/exitHouse. Set `true` for the duration
  // of a scene transition; the top guards on both methods check this flag
  // to prevent double-entry (e.g. a door hit firing mid-fade) and
  // double-exit (e.g. ESC pressed while the exit fade is still running).
  private _transitioning = false

  // Last reason takeoverCharacter bailed — surfaced to the UI so iPad
  // users can see why "Take control" did nothing (no console access).
  private _takeoverBailReason: string | null = null
  get takeoverBailReason(): string | null { return this._takeoverBailReason }

  // Garden takeover (player controls their character)
  private takeoverCtrl: TakeoverController | null = null
  private takeoverCam: TakeoverCamera | null = null
  private takeoverUI: TakeoverUI | null = null
  private takeoverProximity: ProximitySystem | null = null
  private takeoverUserId: string | null = null
  private vehicleCtrl: VehicleController | null = null
  private vehicleSystem: VehicleSystem | null = null
  /** Set of unlocked vehicle IDs — gates V-key mount. */
  private vehicleUnlocks = new Set<string>()
  // Throttle move broadcasts to OrgRoom at ~20Hz during takeover
  private takeoverMoveAccumulator = 0
  private seatToggleCooldown = 0
  /** When true, `onUpdate` renders wireframe boxes over every Rapier collider. */
  private _debugColliders = false
  /** Tracks which users we've already claimed greeting bonus for (per session). */
  private _greetedUsers = new Set<string>()
  private currentOccupiedSeatId: string | null = null
  /** Tracks which seat each remote member occupies (userId → seatId). */
  private remoteSeatMap = new Map<string, string>()
  /** Name of the zone the player is currently inside (during takeover). */
  private _currentZone: string | null = null
  private static readonly TAKEOVER_MOVE_INTERVAL = 0.05  // seconds

  /** The currently authenticated user — set by Vue layer via setCurrentUser(). */
  private currentUser: {
    id: string
    name: string
    characterModel: string | null
    token: string | null
  } | null = null

  /** OrgRoom multiplayer client — connected on setData() when server-driven mode is enabled. */
  private orgRoomClient: OrgRoomClient | null = null
  private connectedOrgId: string | null = null
  private serverDrivenEnabled = false

  // ─── setData serialization ──────────────────────
  // Prevents concurrent SceneManager.rebuild() calls from racing via the
  // buildId cancellation pattern. The SerializedExecutor coalesces rapid
  // setData calls (latest wins) and forwards an AbortSignal so disposal
  // cleanly aborts any in-flight rebuild.
  //
  // Post-build wiring (server-driven flag, OrgRoom callback rebind) goes in
  // `onDrained` so it runs exactly ONCE after all coalesced builds finish,
  // not per-iteration. Per-iteration wiring would replay OrgRoom snapshots
  // through spawnFromSnapshot N times, triggering duplicate GLB load attempts.
  private sceneBuildExecutor = new SerializedExecutor<EngineData>(
    (data, signal) => this.runSceneBuild(data, signal),
    {
      logLabel: 'GardenEngine.setData',
      onDrained: () => this.afterSceneBuildDrained(),
    },
  )

  constructor() {
    this.events = new EventBus<EngineEvents>()
  }

  /**
   * Initialize the PlayCanvas application.
   * Creates canvas, boots the app with proper PBR lighting, sets up input + camera.
   */
  async init(
    container: HTMLElement,
    width: number,
    height: number,
    callbacks?: EngineCallbacks,
  ): Promise<void> {
    this.callbacks = callbacks ?? {}

    // Create canvas
    this.canvas = document.createElement('canvas')
    this.canvas.style.width = '100%'
    this.canvas.style.height = '100%'
    this.canvas.style.display = 'block'
    container.appendChild(this.canvas)

    // Boot core app with proper PBR lighting pipeline
    this.app = new Application()
    this.app.init(this.canvas, width, height)

    // Input manager
    this.input = new InputManager()
    this.input.init(this.canvas, this.app.app)

    // Camera controller
    this.camera = new CameraController()
    this.camera.init(this.app.camera, this.input)

    // Material factory
    this.materials = new MaterialFactory()

    // Scene manager — orchestrates all Phase 2+ subsystems
    this.sceneManager = new SceneManager(this.app, this.materials)

    // Picking system — hover tooltips + click for repo/feature entities
    this.picker = new TreePickerSystem()

    // Interior manager — house exploration mode
    this.interior = new InteriorManager(
      this.app, this.input, this.materials, this.canvas, container,
    )
    this.interior.onExit = () => this.exitHouse()

    // Coffee bar manager — shared break-room interior with queue + brewing
    this.coffeeBar = new CoffeeBarManager(
      this.app, this.input, this.materials, this.canvas, container,
    )
    this.coffeeBar.onExit = () => this.exitCoffeeBar()

    // Cafeteria manager — shared dining interior with queue + cooking
    this.cafeteria = new CafeteriaManager(
      this.app, this.input, this.canvas, container,
    )
    this.cafeteria.onExit = () => this.exitCafeteria()

    // Wire up frame update
    this.app.setConfig({
      onUpdate: (dt) => this.onUpdate(dt),
    })

    // Show controls help overlay (auto-fades after 6s)
    this.camera.showControlsHelp(container)

    this.callbacks.onSceneReady?.()
  }

  /**
   * The error from the most recent failed rebuild, or null if the last build
   * succeeded. Useful for surfacing transient failures in upstream UI without
   * the executor having to reject the `setData` promise.
   */
  get lastBuildError(): unknown { return this.sceneBuildExecutor.lastError }

  /**
   * Receive engine data and build/rebuild the scene.
   *
   * Serialized via SerializedExecutor: if a rebuild is already in progress,
   * this call waits for the drain to finish. Concurrent calls coalesce —
   * only the LATEST `data` is actually built, older superseded values are
   * silently dropped. Every caller's await resolves only after the latest
   * data has been fully applied and OrgRoom callbacks are wired against
   * the fresh subsystems.
   *
   * Semantic note: the `data:set` event fires once per CALLER (even when
   * coalescing drops the caller's data) — subscribers get notified at the
   * rate calls come in, not the rate at which rebuilds actually run.
   */
  async setData(data: EngineData): Promise<void> {
    if (!this.app || !this.sceneManager) return
    // Fire the event per-caller so subscribers preserve their original
    // 1:1 "I was called" semantics even when the executor coalesces.
    this.events.emit('data:set', data)
    return this.sceneBuildExecutor.submit(data)
  }

  /**
   * The runner invoked by SerializedExecutor for each drain iteration.
   * ONLY runs the rebuild — post-build wiring lives in `afterSceneBuildDrained`
   * so it fires once per coalesced burst, not once per iteration.
   *
   * Captures `sceneManager` as a local before the await so a destroy()
   * mid-rebuild can't NPE us. The signal is forwarded into SceneManager.rebuild
   * so it can bail at any internal await checkpoint via signal.throwIfAborted().
   */
  private async runSceneBuild(data: EngineData, signal: AbortSignal): Promise<void> {
    const sceneManager = this.sceneManager
    if (!sceneManager) return
    await sceneManager.rebuild(data, signal)
  }

  /**
   * Called by SerializedExecutor exactly once after all queued setData
   * builds have drained successfully. Re-applies the server-driven flag
   * and re-binds OrgRoom callbacks against the freshly-built subsystems.
   *
   * Re-captures `this.sceneManager` as a local in case a future refactor
   * adds awaits between checks (TOCTOU defense).
   */
  private afterSceneBuildDrained(): void {
    const sm = this.sceneManager
    if (!sm) return
    if (this.serverDrivenEnabled) {
      sm.agentSystemRef?.setServerDriven(true)
    }
    if (this.orgRoomClient?.isConnected) {
      this.wireOrgRoomCallbacks()
    }
  }

  /**
   * Enable server-driven character mode.
   * Must be called BEFORE setData() for the effect to apply cleanly.
   * CharacterSystem is always server-driven (local sim was removed in Phase 9);
   * AgentCharacterSystem still needs the flag to suppress its legacy paths.
   */
  enableServerDriven(enabled: boolean): void {
    this.serverDrivenEnabled = enabled
    this.sceneManager?.agentSystemRef?.setServerDriven(enabled)
  }

  /**
   * Connect to the Colyseus OrgRoom for server-driven character state.
   * When connected, CharacterSystem becomes a renderer for server state
   * instead of simulating NPCs locally.
   *
   * Safe to call multiple times — idempotent per orgId.
   */
  async connectToOrgRoom(orgId: string): Promise<void> {
    if (!this.sceneManager || !this.currentUser) {
      console.warn('[GardenEngine] Cannot connect to OrgRoom — sceneManager or currentUser not set')
      return
    }
    if (this.connectedOrgId === orgId && this.orgRoomClient?.isConnected) return

    const charSystem = this.sceneManager.characterSystemRef
    if (!charSystem) {
      console.warn('[GardenEngine] CharacterSystem not ready — cannot enable server-driven mode')
      return
    }

    // Disconnect previous if org changed
    if (this.orgRoomClient && this.connectedOrgId !== orgId) {
      await this.orgRoomClient.disconnect()
    }

    this.orgRoomClient = OrgRoomClient.getInstance()
    this.wireOrgRoomCallbacks()

    try {
      await this.orgRoomClient.connect(orgId, {
        userId: this.currentUser.id,
        name: this.currentUser.name,
        characterModel: this.currentUser.characterModel ?? '',
        token: this.currentUser.token ?? '',
      })
      this.connectedOrgId = orgId
      this.sceneManager.agentSystemRef?.setServerDriven(true)
      console.debug('[GardenEngine] Connected to OrgRoom org=', orgId)
    } catch (err) {
      console.warn('[GardenEngine] OrgRoom connect failed — continuing in local mode:', err)
      this.orgRoomClient = null
      this.connectedOrgId = null
    }
  }

  /**
   * Bind OrgRoomClient callbacks to the CURRENT Character + Agent system
   * instances. Must be re-invoked after any `SceneManager.rebuild` because
   * rebuild replaces both subsystems — the callbacks captured previously
   * would point at the torn-down instances.
   *
   * Also replays cached member/agent snapshots to the fresh systems so they
   * don't miss members who were added before the rebuild.
   */
  private wireOrgRoomCallbacks(): void {
    if (!this.orgRoomClient || !this.sceneManager) return
    const charSystem = this.sceneManager.characterSystemRef
    if (!charSystem) return
    const agentSystem = this.sceneManager.agentSystemRef

    // (Re)create VehicleSystem for remote player vehicle rendering.
    // Destroyed + recreated on scene rebuild to match CharacterSystem lifecycle.
    this.vehicleSystem?.destroy()
    const gardenRoot = this.sceneManager.gardenRootEntity
    if (gardenRoot) {
      this.vehicleSystem = new VehicleSystem(this.sceneManager.assetLoader, gardenRoot)
      this.vehicleSystem.setLocalUserId(this.currentUser?.id ?? null)
      // Let CharacterSystem skip position updates for mounted characters
      charSystem.isUserMounted = (userId) => this.vehicleSystem?.isMounted(userId) ?? false
    }

    this.orgRoomClient.onMemberAdd = (_userId, snapshot) => {
      void charSystem.spawnFromSnapshot(snapshot)
      this.syncSeatOccupancy(snapshot.userId, snapshot)
    }
    this.orgRoomClient.onMemberUpdate = (_userId, snapshot) => {
      charSystem.updateFromSnapshot(snapshot)
      this.syncRemoteVehicle(charSystem, snapshot)
      this.syncSeatOccupancy(snapshot.userId, snapshot)
      this.syncHouseLevel(snapshot)
    }
    this.orgRoomClient.onMemberRemove = (userId) => {
      this.vehicleSystem?.unregisterCharacter(userId)
      charSystem.removeByUserId(userId)
      this.releaseSeatForMember(userId)
    }

    if (agentSystem) {
      this.orgRoomClient.onAgentAdd = (_agentId, snapshot) => {
        void agentSystem.spawnFromAgentSnapshot(snapshot)
      }
      this.orgRoomClient.onAgentUpdate = (_agentId, snapshot) => {
        agentSystem.updateFromAgentSnapshot(snapshot)
      }
      this.orgRoomClient.onAgentRemove = (agentId) => {
        agentSystem.removeByAgentId(agentId)
      }
    }

    // Replay cached snapshots so the freshly-rebuilt systems render everything
    // that was present before the rebuild. First-connect replays are no-ops
    // because the cache is empty until after `room.joinOrCreate` resolves.
    for (const [, snapshot] of this.orgRoomClient.members) {
      // Spawn character first, then sync vehicle once the entity is ready.
      // spawnFromSnapshot is async (GLB load), so vehicle sync runs after.
      void charSystem.spawnFromSnapshot(snapshot).then(() => {
        this.syncRemoteVehicle(charSystem, snapshot)
      })
    }
  }

  /**
   * Sync a remote player's vehicle state from their snapshot.
   * Skips the local takeover user (local mount is handled by VehicleController).
   */
  private syncRemoteVehicle(
    charSystem: CharacterSystem,
    snapshot: MemberStateSnapshot,
  ): void {
    if (!this.vehicleSystem) return

    // Lazily register the character entity for parenting
    const entity = charSystem.getEntity(snapshot.userId)
    if (entity) this.vehicleSystem.registerCharacter(snapshot.userId, entity)

    void this.vehicleSystem.updateFromSnapshot({
      userId: snapshot.userId,
      vehicleId: snapshot.vehicleId,
      x: snapshot.x,
      z: snapshot.z,
      yaw: snapshot.yaw,
    })
  }

  // ─── House level live sync ────────────────────

  /** Track previous houseLevel per member to detect changes. */
  private memberHouseLevels = new Map<string, number>()

  /**
   * Detect houseLevel changes and rebuild the member's house in the village.
   * If the current user is inside the changed house, exit first.
   */
  private syncHouseLevel(snapshot: MemberStateSnapshot): void {
    const prev = this.memberHouseLevels.get(snapshot.userId)
    const curr = snapshot.houseLevel
    this.memberHouseLevels.set(snapshot.userId, curr)

    if (prev !== undefined && prev !== curr && this.sceneManager) {
      // If we're inside this member's house, exit first
      if (this.sceneState === 'interior' && this._interiorMemberId === snapshot.userId) {
        void this.exitHouse()
      }
      // Rebuild the exterior house with new tier, then refresh physics colliders
      // so walls/door match the new footprint. Physics must run after visual
      // because rebuildByMemberId updates memberHouseMap and rebuildHousePhysics
      // reads from it.
      const sceneManager = this.sceneManager
      void sceneManager.housingVillageRef
        ?.rebuildByMemberId(snapshot.userId, curr)
        .then(() => sceneManager.rebuildHousePhysics(snapshot.userId))
    }
  }

  // ─── Seat occupancy sync ──────────────────────

  /**
   * Sync a remote member's seat occupancy from their server snapshot.
   * If the member is sitting near an InteractionPoint, mark it occupied.
   * If they moved away or stopped sitting, release the old seat.
   * Skip the local takeover user — their seat is managed locally.
   */
  private syncSeatOccupancy(
    userId: string,
    snapshot: { x: number; z: number; animState: string },
  ): void {
    if (userId === this.takeoverUserId) return
    const layout = this.sceneManager?.worldLayout
    if (!layout) return

    const prevSeatId = this.remoteSeatMap.get(userId)
    const isSitting = snapshot.animState === 'sit'

    if (isSitting) {
      // Find nearest seat to this member's position
      const seats = layout.getSeats()
      let nearestId: string | null = null
      let nearestDist = 1.0  // max 1 unit proximity
      for (const s of seats) {
        const dx = snapshot.x - s.x
        const dz = snapshot.z - s.z
        const dist = dx * dx + dz * dz
        if (dist < nearestDist) {
          nearestDist = dist
          nearestId = s.id
        }
      }
      if (nearestId && nearestId !== prevSeatId) {
        if (prevSeatId) layout.release(prevSeatId)
        layout.occupy(nearestId, userId)
        this.remoteSeatMap.set(userId, nearestId)
      }
    } else if (prevSeatId) {
      layout.release(prevSeatId)
      this.remoteSeatMap.delete(userId)
    }
  }

  /** Release any seat occupied by this member (on remove or disconnect). */
  private releaseSeatForMember(userId: string): void {
    const seatId = this.remoteSeatMap.get(userId)
    if (seatId) {
      this.sceneManager?.worldLayout.release(seatId)
      this.remoteSeatMap.delete(userId)
    }
  }

  /** Temporary dev tool: simulate a dev_activity event for the current user. */
  simulateDevActivity(): void {
    this.orgRoomClient?.sendSimulateDevActivity()
  }

  /** Disconnect from the org room (on unmount/destroy). */
  async disconnectOrgRoom(): Promise<void> {
    if (this.orgRoomClient) {
      await this.orgRoomClient.disconnect()
      this.orgRoomClient = null
      this.connectedOrgId = null
    }
    this.sceneManager?.agentSystemRef?.setServerDriven(false)
    this.vehicleSystem?.destroy()
    this.vehicleSystem = null
  }

  /** Per-frame update — called by core app. */
  private onUpdate(dt: number): void {
    switch (this.sceneState) {
      case 'garden':
        this.camera?.update(dt)
        this.sceneManager?.update(dt)
        // VehicleSystem per-frame tick — flips stopped remote horses back
        // to Idle anim when no snapshot arrives for a while.
        this.vehicleSystem?.update()
        if (this.picker && this.app && this.input) {
          const pickables = this.sceneManager?.getPickableEntities() ?? []
          this.picker.update(this.app.camera, this.input, pickables, this.callbacks)
        }
        break

      case 'interior':
        this.interior?.update(dt)
        // Skip sceneManager.update() — garden animations (birds, clouds, trees)
        // are invisible during interior mode and waste CPU cycles.
        break

      case 'coffeebar':
        this.coffeeBar?.update(dt)
        // Same reasoning as 'interior' — garden is hidden, no tick needed.
        break

      case 'cafeteria':
        this.cafeteria?.update(dt)
        break

      case 'takeover':
        // Garden stays alive — birds, clouds, agent robots, other characters.
        // viewerPos drives ProceduralTreeSystem's distance-LOD: trees beyond
        // ~45 units of the local player are removed from the render pass to
        // keep WebGL command submission inside the frame budget. When mounted,
        // the vehicle's position is authoritative for the player; otherwise
        // the takeover capsule's position is used.
        {
          const viewerPos = this.vehicleCtrl?.isActive
            ? (this.vehicleCtrl.getPosition() ?? this.takeoverCtrl?.getPosition() ?? null)
            : (this.takeoverCtrl?.getPosition() ?? null)
          this.sceneManager?.update(dt, viewerPos)
        }
        // Same stopped-horse idle fix as 'garden' — applies here because the
        // local player may be observing other mounted users from takeover.
        this.vehicleSystem?.update()
        if (this.takeoverCtrl && this.takeoverCam) {
          // TakeoverController always runs (handles inactivity even when mounted)
          this.takeoverCtrl.update(dt, this.takeoverCam.yaw)

          // When mounted, VehicleController drives actual movement + camera
          if (this.vehicleCtrl?.isActive) {
            this.vehicleCtrl.update(dt, this.takeoverCam.yaw)
            const vPos = this.vehicleCtrl.getPosition()
            if (vPos) this.takeoverCam.update(vPos)
          } else {
            this.takeoverCam.update(this.takeoverCtrl.getPosition())
          }

          // Throttled broadcast to OrgRoom — other viewers see us move in real time.
          // Client-side prediction: we drive our own entity locally; CharacterSystem
          // ignores incoming snapshot updates for our takeoverUserId.
          if (this.orgRoomClient?.isConnected && this.takeoverUserId) {
            this.takeoverMoveAccumulator += dt
            if (this.takeoverMoveAccumulator >= GardenEngine.TAKEOVER_MOVE_INTERVAL) {
              this.takeoverMoveAccumulator = 0
              // When mounted, position + yaw come from the vehicle
              const vPos = this.vehicleCtrl?.isActive ? this.vehicleCtrl.getPosition() : null
              const pos = vPos ?? this.takeoverCtrl.getPosition()
              const yaw = this.vehicleCtrl?.isActive
                ? this.vehicleCtrl.getYaw()
                : this.takeoverCtrl.getYaw()
              const animState = this.vehicleCtrl?.isActive ? 'sit' : this.takeoverCtrl.getAnimState()
              this.orgRoomClient.sendMove(pos.x, pos.y, pos.z, yaw, animState)
            }
          }

          // Proximity detection
          if (this.takeoverProximity && this.takeoverUI && this.takeoverUserId) {
            const chars = this.sceneManager?.characterSystemRef?.getCharacters() ?? []
            this.takeoverProximity.update(
              this.takeoverCtrl.getPosition(),
              this.takeoverUserId,
              chars,
              this.takeoverUI,
            )
          }

          // ─── Emotes: 1=Wave, 2=Cheer ────────────────────────────────
          if (this.input?.wasPressed(pc.KEY_1)) {
            this.takeoverCtrl.playEmote(1)
            this.tryClaimGreetingBonus()
          }
          if (this.input?.wasPressed(pc.KEY_2)) {
            this.takeoverCtrl.playEmote(2)
            this.tryClaimGreetingBonus()
          }

          // ─── Proximity hotkeys: 3=Greet nearby, 4=Invite to race ────
          // These mirror the action panel's chip buttons. No-op when
          // the proximity system hasn't locked onto a nearby member,
          // so the keys don't misfire in open space. Wave animation is
          // added on Greet so the key press has kinetic feedback that
          // matches its 👋 label.
          const nearbyId = this.takeoverProximity?.nearbyMemberId ?? null
          const nearbyName = this.takeoverProximity?.nearbyMemberName ?? ''
          if (this.input?.wasPressed(pc.KEY_3) && nearbyId) {
            this.takeoverCtrl.playEmote(1)
            this.tryClaimGreetingBonus()
          }
          if (this.input?.wasPressed(pc.KEY_4) && nearbyId && nearbyName) {
            this.callbacks.onInviteToRace?.(nearbyId, nearbyName)
          }

          // ─── Seat interaction: E-key to sit/stand at nearby chairs ───
          if (this.seatToggleCooldown > 0) this.seatToggleCooldown -= dt
          if (this.input?.wasPressed(pc.KEY_E) && this.sceneManager && !this.vehicleCtrl?.isActive && this.seatToggleCooldown <= 0) {
            this.seatToggleCooldown = 0.3  // 300ms debounce
            if (this.takeoverCtrl.isSitting) {
              // Release the occupied seat
              if (this.currentOccupiedSeatId) {
                this.sceneManager.worldLayout.release(this.currentOccupiedSeatId)
                this.currentOccupiedSeatId = null
              }
              this.takeoverCtrl.standUp()
              this.takeoverUI?.hideSeatPrompt()
              const sp = this.takeoverCtrl.getPosition()
              this.orgRoomClient?.sendMove(sp.x, sp.y, sp.z, this.takeoverCtrl.getYaw(), 'idle')
            } else {
              // Find nearest UNOCCUPIED seat within proximity
              const pos = this.takeoverCtrl.getPosition()
              const seats = this.sceneManager.worldLayout.getSeats()
              const PROXIMITY_SQ = 2.5 * 2.5
              let nearest: typeof seats[number] | null = null
              let nearestDist = PROXIMITY_SQ
              for (const seat of seats) {
                if (seat.occupied) continue
                const dx = pos.x - seat.x
                const dz = pos.z - seat.z
                const distSq = dx * dx + dz * dz
                if (distSq < nearestDist) {
                  nearestDist = distSq
                  nearest = seat
                }
              }
              if (nearest) {
                this.sceneManager.worldLayout.occupy(nearest.id, this.takeoverUserId!)
                this.currentOccupiedSeatId = nearest.id
                this.takeoverCtrl.sitAt(nearest.x, nearest.y, nearest.z, nearest.yaw)
                this.takeoverUI?.hideSeatPrompt()
                this.orgRoomClient?.sendMove(nearest.x, nearest.y, nearest.z, nearest.yaw, 'sit')
              }
            }
          }

          // ─── Vehicle mount/dismount: V-key ───
          if (this.input?.wasPressed(pc.KEY_V) && this.sceneManager && !this.takeoverCtrl.isSitting) {
            if (this.vehicleCtrl?.isActive) {
              // Dismount
              const dismountPos = this.vehicleCtrl.dismount()
              if (dismountPos) {
                this.takeoverCtrl.mounted = false

                this.sceneManager.physicsWorld?.teleportPlayer(dismountPos.x, dismountPos.z)
                this.orgRoomClient?.sendDismountVehicle()
              }
            } else {
              // Mount — default to horse for V1 (must be unlocked)
              const horseDef = getVehicleDef('horse')
              if (horseDef && this.vehicleUnlocks.has('horse') && this.sceneManager.physicsWorld) {
                if (!this.vehicleCtrl) {
                  this.vehicleCtrl = new VehicleController(this.input, this.sceneManager.assetLoader)
                }
                const userId = this.takeoverUserId
                const character = userId ? this.sceneManager.characterSystemRef?.getCharacter(userId) : null
                if (character?.entity && userId) {
                  this.takeoverCtrl.mounted = true
                  const physics = this.sceneManager.physicsWorld
                  const root = this.app!.root
                  this.vehicleCtrl.mount(horseDef, character.entity, physics, root)
                    .then(() => this.orgRoomClient?.sendMountVehicle('horse'))
                    .catch(e => {
                      console.error('[GardenEngine] Vehicle mount failed:', e)
                      if (this.takeoverCtrl) this.takeoverCtrl.mounted = false
                    })
                }
              }
            }
          }

          // Show/hide "Press E to sit" prompt when near a seat
          if (!this.takeoverCtrl.isSitting && !this.vehicleCtrl?.isActive && this.sceneManager) {
            const pos = this.takeoverCtrl.getPosition()
            const seats = this.sceneManager.worldLayout.getSeats()
            const nearSeat = seats.some(s => {
              if (s.occupied) return false
              const dx = pos.x - s.x
              const dz = pos.z - s.z
              return dx * dx + dz * dz < 6.25  // 2.5 unit radius
            })
            if (nearSeat) this.takeoverUI?.showSeatPrompt()
            else this.takeoverUI?.hideSeatPrompt()
          }

          // ─── Zone proximity: fire callbacks when entering/exiting named zones ───
          if (this.sceneManager) {
            const pos = this.takeoverCtrl.getPosition()
            const zones = this.sceneManager.worldLayout.getAllZones()
            let insideZone: string | null = null
            for (const z of zones) {
              if (z.name === 'orchard') continue // orchard overlaps everything
              const dx = pos.x - z.x
              const dz = pos.z - z.z
              if (dx * dx + dz * dz < z.radius * z.radius) {
                insideZone = z.name
                break
              }
            }
            if (insideZone !== this._currentZone) {
              if (this._currentZone) this.callbacks.onZoneExit?.(this._currentZone)
              this._currentZone = insideZone
              if (insideZone) this.callbacks.onZoneEnter?.(insideZone)
            }

            // Coffee bar walk-through entry — tight proximity around the
            // hut's single front door. Cooldown prevents the exit-teleport
            // from immediately re-triggering entry.
            if (
              !this.takeoverCtrl.isSitting
              && !this.vehicleCtrl?.isActive
              && Date.now() >= this._coffeeBarReentryCooldownMs
            ) {
              const door = this.getCoffeeBarDoorPos()
              if (door) {
                const pos = this.takeoverCtrl.getPosition()
                const dx = pos.x - door.x
                const dz = pos.z - door.z
                if (dx * dx + dz * dz < 0.8 * 0.8) {
                  console.log('[GardenEngine] Coffee bar door hit → entering')
                  this._coffeeBarReentryCooldownMs = Date.now() + 2000
                  // location: 'coffeebar' tells OrgRoom to park the avatar
                  // at locationContext='coffeebar' (no walkHome). Other
                  // clients hide it while the user is inside.
                  this.exitTakeover({ location: 'coffeebar' })
                    .then(() => this.enterCoffeeBar())
                    .catch(e => console.error('[GardenEngine] coffee bar entry failed:', e))
                }
              }
            }

            // Cafeteria walk-through entry — same pattern as coffee bar.
            if (
              this.takeoverCtrl
              && !this.takeoverCtrl.isSitting
              && !this.vehicleCtrl?.isActive
              && Date.now() >= this._cafeteriaReentryCooldownMs
            ) {
              const door = this.getCafeteriaDoorPos()
              if (door) {
                const pos = this.takeoverCtrl.getPosition()
                const dx = pos.x - door.x
                const dz = pos.z - door.z
                if (dx * dx + dz * dz < 0.8 * 0.8) {
                  console.log('[GardenEngine] Cafeteria door hit → entering')
                  this._cafeteriaReentryCooldownMs = Date.now() + 2000
                  // location: 'cafeteria' — see coffee-bar equivalent above.
                  this.exitTakeover({ location: 'cafeteria' })
                    .then(() => this.enterCafeteria())
                    .catch(e => console.error('[GardenEngine] cafeteria entry failed:', e))
                }
              }
            }
          }

          // exitTakeover() above synchronously clears takeoverCtrl; bail out
          // of the rest of the frame so we don't NPE on showWarning / etc.
          if (!this.takeoverCtrl) break

          // Inactivity warning / auto-exit
          if (this.takeoverCtrl.showWarning) {
            this.takeoverUI?.showWarning(this.takeoverCtrl.warningSecondsLeft)
          } else {
            this.takeoverUI?.hideWarning()
          }

          // Exit triggers — exitTakeover() has its own re-entry guard via !this.takeoverCtrl
          if (this.takeoverCtrl.isInactive) {
            console.log('[GardenEngine] Inactivity timeout → exit takeover')
            this.exitTakeover().catch(e => console.error('[GardenEngine] auto-exit failed:', e))
          } else {
            const door = this.takeoverCtrl.consumeDoorHit()
            if (door) {
              console.log('[GardenEngine] Door hit:', door.doorId, '→ entering house')
              this.exitTakeover()
                .then(() => this.enterHouse(door.doorId))  // doorId = memberId
                .catch(e => console.error('[GardenEngine] door entry failed:', e))
            } else if (this.input?.wasPressed(pc.KEY_ESCAPE)) {
              console.log('[GardenEngine] ESC pressed → exit takeover')
              this.exitTakeover().catch(e => console.error('[GardenEngine] ESC exit failed:', e))
            }
          }
        }
        break

      case 'entering':
      case 'exiting':
        // Transitions in progress — let camera complete any fly-to, skip input
        this.camera?.update(dt)
        break
    }

    // Collider wireframes — drawn last so they overlay other geometry.
    // Active in garden + takeover (skipped in interior since physics is garden-only).
    if (this._debugColliders && this.app
        && (this.sceneState === 'garden' || this.sceneState === 'takeover')) {
      const physics = this.sceneManager?.physicsWorld
      if (physics) drawColliderWireframes(this.app, physics)
    }
  }

  // ─── Interior exploration ─────────────────────────────

  /** Enter a house interior by member ID. */
  async enterHouse(memberId: string): Promise<void> {
    console.debug('[GardenEngine] enterHouse called for', memberId, 'sceneState=', this.sceneState)
    if (this.sceneState !== 'garden' || this._transitioning) {
      console.warn('[GardenEngine] enterHouse blocked: sceneState=', this.sceneState, 'transitioning=', this._transitioning)
      return
    }
    if (!this.camera || !this.interior || !this.sceneManager) {
      console.warn('[GardenEngine] enterHouse blocked: missing', !this.camera ? 'camera' : '', !this.interior ? 'interior' : '', !this.sceneManager ? 'sceneManager' : '')
      return
    }
    const house = this.sceneManager.memberHouseMap.get(memberId)
    if (!house) {
      console.warn('[GardenEngine] enterHouse: no house for memberId=', memberId, 'map keys:', [...this.sceneManager.memberHouseMap.keys()])
      return
    }

    this._transitioning = true
    try {
      this.sceneState = 'entering'
      this._interiorMemberId = memberId
      this.savedCameraState = this.camera.saveState()

      // Fly camera to house position
      const housePos = house.entity.getPosition()
      this.camera.focusOnPosition(housePos, 8)

      // Wait for fly-to transition, then fade to interior
      await this.waitForTransition(800)

      try {
        await this.interior.sceneTransition.perform(async () => {
          // Hide garden world — grass, rocks, trees, buildings all disappear
          const gardenRoot = this.sceneManager?.gardenRootEntity
          if (gardenRoot) gardenRoot.enabled = false

          this.camera!.disable()

          // Suppress door hits for 500 ms across the transition so any
          // stale collision from the frame we entered on can't bleed
          // through to whoever reads doors next (e.g. the interior exit
          // check or the upcoming takeover re-entry).
          this.sceneManager?.physicsWorld?.disableDoorsUntil(Date.now() + 500)

          // Build visitor identity from the authenticated user (not the house owner).
          // This keeps the visitor's own character model and broadcasts their identity
          // to the multiplayer room so other clients see them correctly.
          const visitor = this.currentUser ? {
            userId: this.currentUser.id,
            name: this.currentUser.name,
            characterModel: this.currentUser.characterModel,
          } : null
          console.debug('[GardenEngine] Entering house as visitor:', visitor)
          await this.interior!.enter(house, visitor)
          this.sceneState = 'interior'
          this.events.emit('interior:enter', { memberId, memberName: house.memberName })
        })
      } catch (err) {
        // Recover from failed transition — don't leave sceneState stuck
        console.error('[GardenEngine] Failed to enter house:', err)
        this.sceneState = 'garden'
        this._interiorMemberId = null
        this.camera.enable()
        const gardenRoot = this.sceneManager?.gardenRootEntity
        if (gardenRoot) gardenRoot.enabled = true
        if (this.savedCameraState) {
          this.camera.restoreState(this.savedCameraState)
          this.savedCameraState = null
        }
      }
    } finally {
      this._transitioning = false
    }
  }

  /** Exit the house interior back to garden. */
  async exitHouse(): Promise<void> {
    if (this.sceneState !== 'interior' || this._transitioning) return
    if (!this.camera || !this.interior) return

    // Remember which house we're exiting (for takeover spawn position)
    const exitMemberId = this._interiorMemberId
    const visitorId = this.currentUser?.id ?? exitMemberId

    this._transitioning = true
    try {
      this.sceneState = 'exiting'

      await this.interior.sceneTransition.perform(() => {
        this.interior!.exit()

        // Restore garden world visibility
        const gardenRoot = this.sceneManager?.gardenRootEntity
        if (gardenRoot) gardenRoot.enabled = true

        this.camera!.enable()
        if (this.savedCameraState) {
          this.camera!.restoreState(this.savedCameraState)
          this.savedCameraState = null
        }

        // Teleport the visitor to the door-safe exit position of the
        // house they just left. `HouseResult.exitPosition` is computed at
        // build time (HouseBuilder) and rotated into world coords by
        // HousingVillage, so this is a one-line lookup — no runtime
        // geometry math and no zone-perimeter approximation.
        const house = exitMemberId
          ? this.sceneManager?.memberHouseMap.get(exitMemberId)
          : null
        if (house && visitorId) {
          const character = this.sceneManager?.characterSystemRef?.getCharacter(visitorId)
          if (character) {
            const exit = exitPositionWorld(house)
            character.entity.setPosition(exit.x, 0, exit.z)
            character.entity.setEulerAngles(0, exit.yaw, 0)
            character.entity.anim?.setBoolean('sitting', false)
            character.entity.anim?.setInteger('speed', 0)
          }
        }

        // Block door re-trigger for 500 ms while the new takeover
        // physics capsule is being created. TakeoverController.enter
        // also installs its own 300 ms hard-gate on top — the physics
        // world honors whichever is longer (see
        // `PhysicsWorld.consumeDoorHit`).
        this.sceneManager?.physicsWorld?.disableDoorsUntil(Date.now() + 500)

        this.sceneState = 'garden'
        this.events.emit('interior:exit')
      })

      this._interiorMemberId = null
    } finally {
      this._transitioning = false
    }

    // Re-attach WASD takeover on the visitor. Pass the exit position so
    // the physics capsule spawns there — without it, the async animation
    // load yields to the event loop and a server-driven position update
    // can snap the character to their sim position (bed/desk) before the
    // capsule is created.
    if (visitorId) {
      const exitHouse = exitMemberId
        ? this.sceneManager?.memberHouseMap.get(exitMemberId)
        : null
      const exitPos = exitHouse ? exitPositionWorld(exitHouse) : null
      await this.takeoverCharacter(visitorId, exitPos ?? undefined)
    }
  }

  // ─── Coffee bar interior ──────────────────────────────

  /**
   * World position of the coffee bar's single front door. The hut is
   * centered in X on the zone and pushed back by COFFEE_DOOR_LOCAL_Z,
   * so the door sits at (zone.x, zone.z + COFFEE_DOOR_LOCAL_Z) in world.
   */
  private getCoffeeBarDoorPos(): { x: number; z: number } | null {
    const zone = this.sceneManager?.worldLayout.getZone('coffee_bar')
    if (!zone) return null
    return { x: zone.x, z: zone.z + COFFEE_DOOR_LOCAL_Z }
  }

  /** Position one step outside the door — used as the exit spawn. */
  private getCoffeeBarOutsidePos(): { x: number; z: number; yaw: number } | null {
    const door = this.getCoffeeBarDoorPos()
    if (!door) return null
    return { x: door.x, z: door.z + 1.0, yaw: 0 }
  }

  /**
   * Enter the shared coffee bar interior. Fade-to-black, hide garden,
   * hand control to CoffeeBarManager. Falls back to placeholder identity
   * so dev / unauthenticated sessions still work.
   */
  async enterCoffeeBar(): Promise<void> {
    if (this.sceneState !== 'garden' || this._transitioning) {
      console.warn('[GardenEngine] enterCoffeeBar blocked: sceneState=', this.sceneState, 'transitioning=', this._transitioning)
      return
    }
    if (!this.camera || !this.coffeeBar || !this.sceneManager) return

    const visitorUserId = this.currentUser?.id ?? this.takeoverUserId ?? 'local_visitor'
    const visitorName = this.currentUser?.name ?? 'Visitor'
    const visitorCharacterModel = this.currentUser?.characterModel ?? null
    const orgId = this.connectedOrgId ?? 'local'

    this._transitioning = true
    try {
      this.sceneState = 'entering'
      this.savedCameraState = this.camera.saveState()

      try {
        await this.coffeeBar.sceneTransition.perform(async () => {
          const gardenRoot = this.sceneManager?.gardenRootEntity
          if (gardenRoot) gardenRoot.enabled = false

          this.camera!.disable()
          this.sceneManager?.physicsWorld?.disableDoorsUntil(Date.now() + 500)

          await this.coffeeBar!.enter({
            userId: visitorUserId,
            name: visitorName,
            characterModel: visitorCharacterModel,
            orgId,
          })
          this.sceneState = 'coffeebar'
        })
      } catch (err) {
        console.error('[GardenEngine] Failed to enter coffee bar:', err)
        this.sceneState = 'garden'
        this.camera.enable()
        const gardenRoot = this.sceneManager?.gardenRootEntity
        if (gardenRoot) gardenRoot.enabled = true
        if (this.savedCameraState) {
          this.camera.restoreState(this.savedCameraState)
          this.savedCameraState = null
        }
      }
    } finally {
      this._transitioning = false
    }
  }

  /** Exit the coffee bar interior back to the garden. */
  async exitCoffeeBar(): Promise<void> {
    if (this.sceneState !== 'coffeebar' || this._transitioning) return
    if (!this.camera || !this.coffeeBar) return

    const visitorId = this.currentUser?.id ?? null

    // Lock the visitor under takeover before the fade so stale
    // locationContext="coffeebar" snapshots can't re-hide the avatar
    // during the transition. See exitCafeteria for the full rationale.
    if (visitorId) {
      this.sceneManager?.characterSystemRef?.setTakeoverUser(visitorId)
    }

    this._transitioning = true
    try {
      this.sceneState = 'exiting'

      await this.coffeeBar.sceneTransition.perform(() => {
        this.coffeeBar!.exit()

        const gardenRoot = this.sceneManager?.gardenRootEntity
        if (gardenRoot) gardenRoot.enabled = true

        this.camera!.enable()
        if (this.savedCameraState) {
          this.camera!.restoreState(this.savedCameraState)
          this.savedCameraState = null
        }

        // Teleport the visitor's world character to just outside the door
        const outside = this.getCoffeeBarOutsidePos()
        if (outside && visitorId) {
          const character = this.sceneManager?.characterSystemRef?.getCharacter(visitorId)
          if (character) {
            // Force visible — hidden by snapshot updates during the visit.
            character.entity.enabled = true
            character.entity.setPosition(outside.x, 0, outside.z)
            character.entity.setEulerAngles(0, outside.yaw, 0)
            character.entity.anim?.setBoolean('sitting', false)
            character.entity.anim?.setInteger('speed', 0)
          }
        }

        // Cooldown blocks the walk-through trigger on the exit frame
        this._coffeeBarReentryCooldownMs = Date.now() + 2000
        this.sceneManager?.physicsWorld?.disableDoorsUntil(Date.now() + 500)
        this.sceneState = 'garden'
      })
    } catch (err) {
      // Fade / entity mutations threw. Unwind the pre-fade takeover claim
      // so the local user's avatar is not silently frozen forever by
      // updateFromSnapshot's takeoverUserId early-return, and drop the
      // stuck 'exiting' state back to 'garden'.
      console.error('[GardenEngine] Failed to exit coffee bar:', err)
      this.sceneManager?.characterSystemRef?.setTakeoverUser(null)
      this.sceneState = 'garden'
    } finally {
      this._transitioning = false
    }

    // Re-attach WASD takeover just outside the door so control feels continuous.
    // Skipped if the transition failed — sceneState would not be 'garden'
    // and takeoverCharacter guards on that already.
    if (visitorId && this.sceneState === 'garden') {
      const outside = this.getCoffeeBarOutsidePos()
      await this.takeoverCharacter(visitorId, outside ?? undefined)
    }
  }

  // ─── Cafeteria interior ──────────────────────────────

  /**
   * World position of the cafeteria's front door. The hut sits centered-in-X
   * and pushed back inside the root entity (like the coffee bar), so
   * CAFETERIA_DOOR_OFFSET carries the door's position relative to the zone
   * center rather than being a simple (width/2, depth) offset.
   */
  private getCafeteriaDoorPos(): { x: number; z: number } | null {
    const zone = this.sceneManager?.worldLayout.getZone('cafeteria')
    if (!zone) return null
    return {
      x: zone.x + CAFETERIA_DOOR_OFFSET.x,
      z: zone.z + CAFETERIA_DOOR_OFFSET.z,
    }
  }

  private getCafeteriaOutsidePos(): { x: number; z: number; yaw: number } | null {
    const door = this.getCafeteriaDoorPos()
    if (!door) return null
    return { x: door.x, z: door.z + 1.0, yaw: 0 }
  }

  /** Enter the shared cafeteria interior. Mirrors enterCoffeeBar. */
  async enterCafeteria(): Promise<void> {
    if (this.sceneState !== 'garden' || this._transitioning) {
      console.warn('[GardenEngine] enterCafeteria blocked: sceneState=', this.sceneState, 'transitioning=', this._transitioning)
      return
    }
    if (!this.camera || !this.cafeteria || !this.sceneManager) return

    const visitorUserId = this.currentUser?.id ?? this.takeoverUserId ?? 'local_visitor'
    const visitorName = this.currentUser?.name ?? 'Visitor'
    const visitorCharacterModel = this.currentUser?.characterModel ?? null
    const orgId = this.connectedOrgId ?? 'local'

    this._transitioning = true
    try {
      this.sceneState = 'entering'
      this.savedCameraState = this.camera.saveState()

      try {
        await this.cafeteria.sceneTransition.perform(async () => {
          const gardenRoot = this.sceneManager?.gardenRootEntity
          if (gardenRoot) gardenRoot.enabled = false
          // Note: CharacterSystem's org-member avatars are hidden by the
          // server-driven locationContext="cafeteria" rule in
          // CharacterSystem.updateFromSnapshot — no need to toggle
          // characterSystem.root here. Matches enterCoffeeBar.

          this.camera!.disable()
          this.sceneManager?.physicsWorld?.disableDoorsUntil(Date.now() + 500)

          await this.cafeteria!.enter({
            userId: visitorUserId,
            name: visitorName,
            characterModel: visitorCharacterModel,
            orgId,
          })
          this.sceneState = 'cafeteria'
        })
      } catch (err) {
        console.error('[GardenEngine] Failed to enter cafeteria:', err)
        // Fully unwind any partial state — if CafeteriaManager.enter()
        // enabled the root before throwing, calling exit() here hides it
        // again and disconnects any in-flight Colyseus join.
        this.cafeteria?.exit()
        this.sceneState = 'garden'
        this.camera.enable()
        const gardenRoot = this.sceneManager?.gardenRootEntity
        if (gardenRoot) gardenRoot.enabled = true
        if (this.savedCameraState) {
          this.camera.restoreState(this.savedCameraState)
          this.savedCameraState = null
        }
      }
    } finally {
      this._transitioning = false
    }
  }

  /** Exit the cafeteria interior back to the garden. */
  async exitCafeteria(): Promise<void> {
    if (this.sceneState !== 'cafeteria' || this._transitioning) return
    if (!this.camera || !this.cafeteria) return

    const visitorId = this.currentUser?.id ?? null

    // Reserve the local user as "under takeover" before any fade work
    // starts. During the visit, OrgRoom has been broadcasting
    // locationContext="cafeteria" snapshots which CharacterSystem uses to
    // hide the avatar. The moment we begin exit, lock the visitor's userId
    // as takeover so updateFromSnapshot ignores any stale "cafeteria"
    // snapshots that arrive during the fade — otherwise the entity stays
    // hidden until a fresh server broadcast resets locationContext.
    if (visitorId) {
      this.sceneManager?.characterSystemRef?.setTakeoverUser(visitorId)
    }

    this._transitioning = true
    try {
      this.sceneState = 'exiting'

      await this.cafeteria.sceneTransition.perform(() => {
        this.cafeteria!.exit()

        const gardenRoot = this.sceneManager?.gardenRootEntity
        if (gardenRoot) gardenRoot.enabled = true

        this.camera!.enable()
        if (this.savedCameraState) {
          this.camera!.restoreState(this.savedCameraState)
          this.savedCameraState = null
        }

        const outside = this.getCafeteriaOutsidePos()
        if (outside && visitorId) {
          const character = this.sceneManager?.characterSystemRef?.getCharacter(visitorId)
          if (character) {
            // Force visible — the entity was disabled by snapshot updates
            // during the visit; enable it here before the fade reveals the
            // garden again.
            character.entity.enabled = true
            character.entity.setPosition(outside.x, 0, outside.z)
            character.entity.setEulerAngles(0, outside.yaw, 0)
            character.entity.anim?.setBoolean('sitting', false)
            character.entity.anim?.setInteger('speed', 0)
          }
        }

        this._cafeteriaReentryCooldownMs = Date.now() + 2000
        this.sceneManager?.physicsWorld?.disableDoorsUntil(Date.now() + 500)
        this.sceneState = 'garden'
      })
    } catch (err) {
      // See exitCoffeeBar — fade failure leaves sceneState='exiting' and
      // the pre-fade takeover claim hiding snapshot updates. Unwind both.
      console.error('[GardenEngine] Failed to exit cafeteria:', err)
      this.sceneManager?.characterSystemRef?.setTakeoverUser(null)
      this.sceneState = 'garden'
    } finally {
      this._transitioning = false
    }

    // Skipped if the transition failed — takeoverCharacter guards on
    // sceneState === 'garden' already.
    if (visitorId && this.sceneState === 'garden') {
      const outside = this.getCafeteriaOutsidePos()
      await this.takeoverCharacter(visitorId, outside ?? undefined)
    }
  }

  /** Helper — wait for a duration (used to let camera fly-to complete). */
  private waitForTransition(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  // ─── Greeting bonus (one-time 1 SP) ──────────────

  /**
   * Claim 1 SP greeting bonus if emoting near another player for the first time.
   * Silent no-op if already claimed or no nearby character.
   */
  private tryClaimGreetingBonus(): void {
    const targetId = this.takeoverProximity?.nearbyMemberId
    if (!targetId) return
    if (this._greetedUsers.has(targetId)) return
    this._greetedUsers.add(targetId)
    import('@/services/api').then(({ default: api }) => {
      api.post('/v1/xp/claim-greeting-bonus', { target_user_id: targetId }).then(res => {
        if (res.data?.awarded) {
          console.log('[GardenEngine] Greeting bonus! +0.25 SP')
          this.takeoverUI?.showCelebration('+0.25 SP — New greeting!')
        }
      }).catch(() => { /* silently ignore — non-critical */ })
    })
  }

  // ─── Debug visualization ─────────────────────────

  /**
   * Toggle wireframe rendering of every Rapier collider (walls, door triggers,
   * player capsule). Exposed so the Vue layer / browser console can flip it
   * at runtime: `window.__engine?.toggleColliderDebug()`.
   * @returns the new enabled state
   */
  toggleColliderDebug(): boolean {
    this._debugColliders = !this._debugColliders
    console.log('[GardenEngine] collider debug =', this._debugColliders)
    return this._debugColliders
  }

  // ─── Garden takeover ─────────────────────────────

  /**
   * Take control of a character in the garden.
   * Camera follows the character, WASD drives movement.
   * @param userId - The member's user_id (must match a character in the scene)
   */
  async takeoverCharacter(
    userId: string,
    spawnOverride?: { x: number; z: number; yaw: number },
  ): Promise<void> {
    // The UI surfaces the bail reason via `takeoverBailReason`; debug
    // logs only fire in dev to avoid console noise in production (and
    // because `_takeoverBailReason` is the primary diagnostic).
    const debug = import.meta.env.DEV
    if (this.sceneState !== 'garden') {
      if (debug) console.warn('[GardenEngine] takeover bail: sceneState =', this.sceneState)
      this._takeoverBailReason = `Scene not ready (${this.sceneState}).`
      return
    }
    if (!this.camera || !this.input || !this.sceneManager || !this.app) {
      const missing = [
        !this.camera && 'camera',
        !this.input && 'input',
        !this.sceneManager && 'sceneManager',
        !this.app && 'app',
      ].filter(Boolean).join(', ')
      if (debug) console.warn('[GardenEngine] takeover bail: missing', missing)
      this._takeoverBailReason = `Engine not initialised (${missing}).`
      return
    }

    const charSystem = this.sceneManager.characterSystemRef
    if (!charSystem) {
      if (debug) console.warn('[GardenEngine] takeover bail: characterSystem not ready')
      this._takeoverBailReason = 'Characters not loaded yet.'
      return
    }

    const character = charSystem.getCharacter(userId)
    if (!character) {
      const available = charSystem.getCharacters().map(c => c.memberId)
      if (debug) {
        console.warn(
          '[GardenEngine] takeoverCharacter: character not found for', userId,
          'available:', available,
        )
      }
      this._takeoverBailReason = available.length
        ? `No character assigned to you yet (${available.length} others in scene).`
        : 'Still connecting — wait for characters to appear.'
      return
    }

    this._takeoverBailReason = null

    // Take Control always enters garden WASD mode. Interior mode (walking
    // around inside the house) is a separate entry point triggered by
    // clicking on the house itself (`onHouseClick` → `enterHouse`). Keeping
    // the two paths distinct avoids the "click Exit, click Take Control,
    // end up back in the house I just left" loop that the overloaded
    // routing used to produce.
    console.log('[GardenEngine] takeoverCharacter → entering garden WASD mode')

    // Determine spawn position: explicit override (from exitHouse) takes
    // priority, otherwise check if the character is inside their own house
    // (server-sim had them at bed/desk) and spit them out the front door.
    if (spawnOverride) {
      character.entity.setPosition(spawnOverride.x, 0, spawnOverride.z)
      character.entity.setEulerAngles(0, spawnOverride.yaw, 0)
      character.entity.anim?.setBoolean('sitting', false)
      character.entity.anim?.setInteger('speed', 0)
      character.entity.anim?.setInteger('working', 0)
      this.sceneManager.physicsWorld?.disableDoorsUntil(Date.now() + 500)
      console.debug('[GardenEngine] spawn override at', { x: spawnOverride.x.toFixed(2), z: spawnOverride.z.toFixed(2), yaw: spawnOverride.yaw })
    } else {
      const ownHouse = this.sceneManager.memberHouseMap.get(userId)
      if (ownHouse && ownHouse.pivot) {
        const cp = character.entity.getPosition()
        const bedW = toWorld(ownHouse.bedPosition, ownHouse.pivot)
        const dx = cp.x - bedW.x
        const dz = cp.z - bedW.z
        const nearBed = (dx * dx + dz * dz) < 9
        const pivot = ownHouse.pivot
        const nearSeat = ownHouse.seats.some(s => {
          const w = toWorld(s, pivot)
          const sx = cp.x - w.x
          const sz = cp.z - w.z
          return (sx * sx + sz * sz) < 4
        })
        if (nearBed || nearSeat) {
          const exit = exitPositionWorld(ownHouse)
          character.entity.setPosition(exit.x, 0, exit.z)
          character.entity.setEulerAngles(0, exit.yaw, 0)
          character.entity.anim?.setBoolean('sitting', false)
          character.entity.anim?.setInteger('speed', 0)
          character.entity.anim?.setInteger('working', 0)
          this.sceneManager.physicsWorld?.disableDoorsUntil(Date.now() + 500)
          console.debug('[GardenEngine] teleported to own house exit at', { x: exit.x.toFixed(2), z: exit.z.toFixed(2), yaw: exit.yaw })
        }
      }
    }

    this.takeoverUserId = userId

    // Save camera state for restoration
    this.savedCameraState = this.camera.saveState()
    this.camera.disable()

    // Block NPC AI for this character
    charSystem.setTakeoverUser(userId)

    // Load extended animations (Sprint, Jump)
    try {
      await loadTakeoverAnimations(character.entity, this.sceneManager.assetLoader)
    } catch (err) {
      console.warn('[GardenEngine] Failed to load takeover animations:', err)
      // Continue anyway — walk/idle will still work from the extended state graph
    }

    // Initialize takeover systems — Rapier physics handles all collision + door detection
    const physics = this.sceneManager.physicsWorld
    if (!physics) {
      console.warn('[GardenEngine] Physics world not available — cannot enter takeover mode')
      charSystem.setTakeoverUser(null)
      this.camera.enable()
      if (this.savedCameraState) {
        this.camera.restoreState(this.savedCameraState)
        this.savedCameraState = null
      }
      return
    }

    this.takeoverCtrl = new TakeoverController(this.input)
    this.takeoverCtrl.enter(character.entity, physics)

    // Re-apply spawn override AFTER capsule creation — the async animation
    // load above can yield to the event loop, allowing a server-driven
    // position update to snap the entity away from the exit position before
    // the capsule reads entity.getPosition().
    if (spawnOverride) {
      character.entity.setPosition(spawnOverride.x, 0, spawnOverride.z)
      character.entity.setEulerAngles(0, spawnOverride.yaw, 0)
      physics.teleportPlayer(spawnOverride.x, spawnOverride.z)
    }

    // Claim server-side takeover: OrgRoom will suspend its NPC sim for this
    // member and accept move messages only from this session.
    this.orgRoomClient?.sendTakeoverStart(userId)
    this.takeoverMoveAccumulator = 0

    this.takeoverCam = new TakeoverCamera()
    this.takeoverCam.enable(this.app.camera, this.canvas!)

    this.takeoverUI = new TakeoverUI()
    this.takeoverUI.init(this.canvas!.parentElement!)
    this.takeoverUI.onExitClick = () => this.exitTakeover()
    // Surface the Invite-to-race target's id + name up to the Vue layer
    // (which opens RaceSetupDialog). Greet has no button callback — it's
    // driven purely by the `3` hotkey in onUpdate.
    this.takeoverUI.onInviteNearbyToRace = (userId, name) => {
      this.callbacks.onInviteToRace?.(userId, name)
    }
    this.takeoverUI.show()

    this.takeoverProximity = new ProximitySystem()

    this.sceneState = 'takeover'
    console.debug('[GardenEngine] Entered takeover mode for', userId)
  }

  /**
   * Exit takeover mode — restore camera and resume NPC behavior.
   *
   * @param opts.location  Optional interior destination the user is
   *   stepping into (e.g. "cafeteria", "coffeebar"). When set, the
   *   server skips walkHome and stamps `member.locationContext = location`,
   *   which every other client's CharacterSystem reads to hide the
   *   avatar while the visit is in progress. Re-acquiring takeover on
   *   exit sends takeover_start, which resets locationContext to
   *   "garden" — the avatar reappears automatically.
   */
  async exitTakeover(opts: { location?: string } = {}): Promise<void> {
    // Re-entry guard: takeoverCtrl is cleared first thing to prevent any concurrent calls
    if (!this.takeoverCtrl) return

    // Dismount vehicle if mounted before exiting takeover
    if (this.vehicleCtrl?.isActive) {
      this.vehicleCtrl.dismount()
      this.takeoverCtrl.mounted = false
    }

    // Release any occupied seat
    if (this.currentOccupiedSeatId && this.sceneManager) {
      this.sceneManager.worldLayout.release(this.currentOccupiedSeatId)
      this.currentOccupiedSeatId = null
    }

    // Immediately transition to 'exiting' state + clear ctrl to block the takeover update loop
    this.sceneState = 'exiting'
    const ctrl = this.takeoverCtrl
    this.takeoverCtrl = null

    // Release server-side takeover. The optional `location` tells the
    // server this is an interior hand-off (cafeteria / coffee bar)
    // rather than a release-to-NPC; the server then parks the avatar
    // at locationContext=location and every viewer hides it.
    if (this.takeoverUserId) {
      this.orgRoomClient?.sendTakeoverEnd(this.takeoverUserId, opts.location)
    }

    // Clear the client-side prediction block BEFORE any async work. Snapshot
    // updates for this member will flow through again — specifically the
    // server's walkHome position advances — so the entity stays in sync with
    // the authoritative server state instead of being snapped back to a
    // stale cached position by ctrl.exit().
    const exitingUserId = this.takeoverUserId
    this.sceneManager?.characterSystemRef?.setTakeoverUser(null)

    const character = exitingUserId
      ? this.sceneManager?.characterSystemRef?.getCharacter(exitingUserId)
      : null

    // Destroy physics player + cancel door detection, but do NOT restore the
    // entity to the pre-takeover position — the server-driven snapshot sync
    // now owns the authoritative location and will walk the character home
    // via DevActivitySim's walkHome path started by handleTakeoverEnd.
    ctrl.exit()

    // Restore locomotion animations (GLB swap). During this await, the
    // server's walkHome ticks stream in as snapshot updates and advance
    // character.entity position naturally — no local snapping needed.
    if (character && this.sceneManager) {
      try {
        await restoreLocomotionAnimations(character.entity, this.sceneManager.assetLoader)
      } catch (err) {
        console.warn('[GardenEngine] Failed to restore locomotion animations:', err)
      }
    }

    // Disable takeover camera and UI
    this.takeoverCam?.disable()
    this.takeoverCam = null
    this.takeoverUI?.hide()
    this.takeoverUI?.destroy()
    this.takeoverUI = null
    this.takeoverProximity?.reset()
    this.takeoverProximity = null

    // Restore garden camera
    if (this.camera) {
      this.camera.enable()
      if (this.savedCameraState) {
        this.camera.restoreState(this.savedCameraState)
        this.savedCameraState = null
      }
    }

    // Clear zone tracking — fire exit callback if inside a zone
    if (this._currentZone) {
      this.callbacks.onZoneExit?.(this._currentZone)
      this._currentZone = null
    }

    this.sceneState = 'garden'
    this.takeoverUserId = null
    console.log('[GardenEngine] Exited takeover mode — server walking home')
  }

  /** Whether the engine is currently in takeover mode. */
  get isTakeover(): boolean { return this.sceneState === 'takeover' }

  /** Current top-level scene state (garden, takeover, interior, etc.). */
  getSceneState(): SceneState { return this._sceneState }

  /**
   * ID of the nearby member the proximity system has locked onto, or
   * null. Used by the on-screen touch overlay to gate the Greet (3) and
   * Invite-to-race (4) buttons so they only light up when there's
   * actually a target.
   */
  getNearbyMemberId(): string | null {
    return this.takeoverProximity?.nearbyMemberId ?? null
  }

  /**
   * Set the currently authenticated user's full identity.
   * The token is forwarded to the Colyseus OrgRoom on connect so the server
   * can verify it via `/internal/colyseus/verify-token` before trusting any
   * client-supplied `userId` / `name` values.
   */
  setCurrentUser(
    user: { id: string; name: string; characterModel: string | null; token: string | null } | null,
  ): void {
    this.currentUser = user
    // Keep VehicleSystem in sync so it always skips the local user
    this.vehicleSystem?.setLocalUserId(user?.id ?? null)
  }

  /** Update the set of unlocked vehicle IDs (gates V-key mount). */
  setVehicleUnlocks(unlocks: string[]): void {
    this.vehicleUnlocks = new Set(unlocks)
  }

  /** True whenever the player is actively controlling a character (takeover OR house interior). */
  get isInControl(): boolean {
    return this.sceneState === 'takeover' || this.sceneState === 'interior'
  }

  /** Toggle relationship arc visibility. Returns new visible state. */
  toggleArcs(): boolean {
    return this.sceneManager?.toggleArcs() ?? false
  }

  /** Focus camera on a specific tree. */
  focusOnRepo(repoName: string): void {
    if (!this.sceneManager || !this.camera) return
    const pos = this.sceneManager.getTreePosition(repoName)
    if (pos) {
      this.camera.focusOnPosition(pos, 15)
    }
  }

  /** Clear tree focus — return to overview. */
  clearFocus(): void {
    this.camera?.setOverviewMode()
  }

  /** Get internal references for Phase 3+ integration. */
  get scene(): SceneManager | null { return this.sceneManager }
  get cameraController(): CameraController | null { return this.camera }
  get inputManager(): InputManager | null { return this.input }
  get application(): Application | null { return this.app }
  get materialFactory(): MaterialFactory | null { return this.materials }

  resize(width: number, height: number): void {
    this.app?.resize(width, height)
  }

  destroy(): void {
    // Dispose the scene-build executor — aborts any in-flight rebuild via
    // its AbortSignal so SceneManager.build can exit early at its next
    // await checkpoint instead of touching nulled refs after destroy.
    // Subsequent setData() calls become no-ops.
    this.sceneBuildExecutor.dispose()

    // Disconnect multiplayer (fire-and-forget — don't block destroy)
    void this.disconnectOrgRoom()

    // Clean up takeover if active
    this.takeoverCtrl?.exit()
    this.takeoverCtrl = null
    this.takeoverCam?.destroy()
    this.takeoverCam = null
    this.takeoverUI?.destroy()
    this.takeoverUI = null
    this.takeoverProximity = null
    this.takeoverUserId = null

    this.interior?.destroy()
    this.interior = null
    this.coffeeBar?.destroy()
    this.coffeeBar = null
    this.cafeteria?.destroy()
    this.cafeteria = null
    this.picker = null
    this.sceneManager?.destroy()
    this.sceneManager = null
    this.events.clear()
    this.materials?.clear()
    this.materials = null
    this.input?.destroy()
    this.input = null
    this.camera?.destroyHelp()
    this.camera = null
    this.app?.destroy()
    this.app = null
    this.sceneState = 'garden'
    this.savedCameraState = null

    if (this.canvas) {
      this.canvas.remove()
      this.canvas = null
    }
  }
}
