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
import { Application } from './core/Application'
import { EventBus } from './core/EventBus'
import { InputManager } from './input/InputManager'
import { CameraController, type CameraState } from './camera/CameraController'
import { MaterialFactory } from './rendering/MaterialFactory'
import { SceneManager } from './core/SceneManager'
import { TreePickerSystem } from './interaction/TreePickerSystem'
import { InteriorManager } from './interior'
import {
  TakeoverController,
  TakeoverCamera,
  TakeoverUI,
  ProximitySystem,
  loadTakeoverAnimations,
  restoreLocomotionAnimations,
} from './takeover'
import { OrgRoomClient } from '../multiplayer'
import { SerializedExecutor } from './utils/SerializedExecutor'

export { type EngineData, type EngineCallbacks } from './types'

type SceneState = 'garden' | 'entering' | 'interior' | 'exiting' | 'takeover'

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
  private sceneState: SceneState = 'garden'
  private savedCameraState: CameraState | null = null
  private _interiorMemberId: string | null = null
  // Re-entrancy guard for enterHouse/exitHouse. Set `true` for the duration
  // of a scene transition; the top guards on both methods check this flag
  // to prevent double-entry (e.g. a door hit firing mid-fade) and
  // double-exit (e.g. ESC pressed while the exit fade is still running).
  private _transitioning = false

  // Garden takeover (player controls their character)
  private takeoverCtrl: TakeoverController | null = null
  private takeoverCam: TakeoverCamera | null = null
  private takeoverUI: TakeoverUI | null = null
  private takeoverProximity: ProximitySystem | null = null
  private takeoverUserId: string | null = null
  // Throttle move broadcasts to OrgRoom at ~20Hz during takeover
  private takeoverMoveAccumulator = 0
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
    this.input.init(this.canvas)

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

    this.orgRoomClient.onMemberAdd = (_userId, snapshot) => {
      void charSystem.spawnFromSnapshot(snapshot)
    }
    this.orgRoomClient.onMemberUpdate = (_userId, snapshot) => {
      charSystem.updateFromSnapshot(snapshot)
    }
    this.orgRoomClient.onMemberRemove = (userId) => {
      charSystem.removeByUserId(userId)
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
      void charSystem.spawnFromSnapshot(snapshot)
    }
  }

  /** Disconnect from the org room (on unmount/destroy). */
  async disconnectOrgRoom(): Promise<void> {
    if (this.orgRoomClient) {
      await this.orgRoomClient.disconnect()
      this.orgRoomClient = null
      this.connectedOrgId = null
    }
    this.sceneManager?.agentSystemRef?.setServerDriven(false)
  }

  /** Per-frame update — called by core app. */
  private onUpdate(dt: number): void {
    switch (this.sceneState) {
      case 'garden':
        this.camera?.update(dt)
        this.sceneManager?.update(dt)
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

      case 'takeover':
        // Garden stays alive — birds, clouds, agent robots, other characters
        this.sceneManager?.update(dt)
        if (this.takeoverCtrl && this.takeoverCam) {
          this.takeoverCtrl.update(dt, this.takeoverCam.yaw)
          this.takeoverCam.update(this.takeoverCtrl.getPosition())

          // Throttled broadcast to OrgRoom — other viewers see us move in real time.
          // Client-side prediction: we drive our own entity locally; CharacterSystem
          // ignores incoming snapshot updates for our takeoverUserId.
          if (this.orgRoomClient?.isConnected && this.takeoverUserId) {
            this.takeoverMoveAccumulator += dt
            if (this.takeoverMoveAccumulator >= GardenEngine.TAKEOVER_MOVE_INTERVAL) {
              this.takeoverMoveAccumulator = 0
              const pos = this.takeoverCtrl.getPosition()
              this.orgRoomClient.sendMove(
                pos.x, pos.y, pos.z,
                this.takeoverCtrl.getYaw(),
                this.takeoverCtrl.getAnimState(),
              )
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
  }

  // ─── Interior exploration ─────────────────────────────

  /** Enter a house interior by member ID. */
  async enterHouse(memberId: string): Promise<void> {
    if (this.sceneState !== 'garden' || this._transitioning) return
    if (!this.camera || !this.interior || !this.sceneManager) return
    const house = this.sceneManager.memberHouseMap.get(memberId)
    if (!house) return

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
            const exit = house.exitPosition
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

    // Re-attach WASD takeover on the visitor. Kept outside the
    // `_transitioning` window so `takeoverCharacter`'s own guards (which
    // check `sceneState === 'garden'`) can run unblocked.
    if (visitorId) {
      await this.takeoverCharacter(visitorId)
    }
  }

  /** Helper — wait for a duration (used to let camera fly-to complete). */
  private waitForTransition(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  // ─── Garden takeover ─────────────────────────────

  /**
   * Take control of a character in the garden.
   * Camera follows the character, WASD drives movement.
   * @param userId - The member's user_id (must match a character in the scene)
   */
  async takeoverCharacter(userId: string): Promise<void> {
    if (this.sceneState !== 'garden' || !this.camera || !this.input || !this.sceneManager || !this.app) return

    const charSystem = this.sceneManager.characterSystemRef
    if (!charSystem) return

    const character = charSystem.getCharacter(userId)
    if (!character) {
      console.warn(
        '[GardenEngine] takeoverCharacter: character not found for', userId,
        '— check that the Colyseus OrgRoom is connected and that the user is',
        'in the org snapshot (see _collect_org_members in internal_colyseus.py).',
      )
      return
    }

    // Take Control always enters garden WASD mode. Interior mode (walking
    // around inside the house) is a separate entry point triggered by
    // clicking on the house itself (`onHouseClick` → `enterHouse`). Keeping
    // the two paths distinct avoids the "click Exit, click Take Control,
    // end up back in the house I just left" loop that the overloaded
    // routing used to produce.
    console.log('[GardenEngine] takeoverCharacter → entering garden WASD mode')

    // If the character is currently inside their own house (e.g. sitting
    // at their desk as the auto-sim had them doing), spit them out the
    // front door BEFORE the physics capsule is created. Without this,
    // `TakeoverController.enter` would spawn the capsule inside the walls
    // and WASD mode would show the garden exterior with the character
    // stuck in interior geometry. We deliberately don't route them to
    // interior mode — the plan keeps takeover == garden WASD and
    // interior is only reached via the house-click or door-walk paths.
    const ownHouse = this.sceneManager.memberHouseMap.get(userId)
    if (ownHouse) {
      const hp = ownHouse.entity.getPosition()
      const cp = character.entity.getPosition()
      // House footprint is 4×4, with HousingVillage placing the entity
      // at a corner (local-origin) and applying a 90° Y rotation. After
      // rotation the world-space AABB is x ∈ [hp.x, hp.x+4], z ∈ [hp.z-4, hp.z].
      const insideX = cp.x >= hp.x - 0.2 && cp.x <= hp.x + 4.2
      const insideZ = cp.z >= hp.z - 4.2 && cp.z <= hp.z + 0.2
      if (insideX && insideZ) {
        const exit = ownHouse.exitPosition
        character.entity.setPosition(exit.x, 0, exit.z)
        character.entity.setEulerAngles(0, exit.yaw, 0)
        character.entity.anim?.setBoolean('sitting', false)
        character.entity.anim?.setInteger('speed', 0)
        // Extend the door cooldown so the first physics tick after
        // capsule creation can't re-fire the door sensor.
        this.sceneManager.physicsWorld?.disableDoorsUntil(Date.now() + 500)
        console.debug('[GardenEngine] teleported', userId, 'to house exit before takeover')
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

    // Claim server-side takeover: OrgRoom will suspend its NPC sim for this
    // member and accept move messages only from this session.
    this.orgRoomClient?.sendTakeoverStart(userId)
    this.takeoverMoveAccumulator = 0

    this.takeoverCam = new TakeoverCamera()
    this.takeoverCam.enable(this.app.camera, this.canvas!)

    this.takeoverUI = new TakeoverUI()
    this.takeoverUI.init(this.canvas!.parentElement!)
    this.takeoverUI.onExitClick = () => this.exitTakeover()
    this.takeoverUI.show()

    this.takeoverProximity = new ProximitySystem()

    this.sceneState = 'takeover'
    console.debug('[GardenEngine] Entered takeover mode for', userId)
  }

  /** Exit takeover mode — restore camera and resume NPC behavior. */
  async exitTakeover(): Promise<void> {
    // Re-entry guard: takeoverCtrl is cleared first thing to prevent any concurrent calls
    if (!this.takeoverCtrl) return

    // Immediately transition to 'exiting' state + clear ctrl to block the takeover update loop
    this.sceneState = 'exiting'
    const ctrl = this.takeoverCtrl
    this.takeoverCtrl = null

    // Release server-side takeover so OrgRoom's walkHome simulation resumes
    // for this member. The server will start advancing position toward the
    // home seat on its next tick.
    if (this.takeoverUserId) {
      this.orgRoomClient?.sendTakeoverEnd(this.takeoverUserId)
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

    this.sceneState = 'garden'
    this.takeoverUserId = null
    console.log('[GardenEngine] Exited takeover mode — server walking home')
  }

  /** Whether the engine is currently in takeover mode. */
  get isTakeover(): boolean { return this.sceneState === 'takeover' }

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
