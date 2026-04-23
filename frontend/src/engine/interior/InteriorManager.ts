// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * InteriorManager — coordinator for the interior exploration mode.
 *
 * Lifecycle: build() → enter(house) → update(dt) per frame → exit() → destroy()
 *
 * Delegates all logic to subsystems:
 *   InteriorScene  — furniture/walls (from housetest SceneConfig)
 *   PlayerController — WASD movement + animations
 *   InteriorCamera   — orbit camera wrapper
 *   InteriorUI       — DOM overlay
 *   InteractionLoop  — proximity + E-key logic
 *   DoorTrigger      — exit detection
 *   SceneTransition  — fade overlay
 *
 * Singleton interior — built once, reused for every house visit.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { InputManager } from '../input/InputManager'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { HouseResult } from '../buildings/HouseBuilder'
import { AssetLoader } from '../assets/AssetLoader'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { InteriorScene } from '../housetest/InteriorScene'
import { PlayerController } from '../housetest/PlayerController'
import { DoorTrigger } from '../housetest/DoorTrigger'
import { SceneTransition } from '../housetest/SceneTransition'
import type { CollisionBox } from '../housetest/CollisionSystem'
import { InteriorCamera } from './InteriorCamera'
import { InteriorUI } from './InteriorUI'
import { InteractionLoop } from './InteractionLoop'
import {
  ColyseusClient,
  NetworkedPlayer,
  OrgRoomClient,
  PlayerSyncAdapter,
  type MemberStateSnapshot,
  type PlayerData,
} from '../../multiplayer'
import { getInteractablesForTier } from '../housetest/SceneConfig'
import { getHouseTierGeometry } from '@shared/world/HouseTiers'

/** Z offset from the back wall for the player's spawn — leaves walking room. */
const PLAYER_ENTER_Z = 1.5

/**
 * Get owner NPC seat position from the tier's interactable config. Reads the
 * actual laptop/bed seat coordinates so positions match the visual furniture;
 * falls back to the tier's canonical desk/bed geometry (shared with physics)
 * when the housetest config is missing the entry.
 */
function getOwnerSeat(tier: number, type: 'desk' | 'bed'): { x: number; z: number; yaw: number } {
  const interactables = getInteractablesForTier(tier)
  const id = type === 'desk' ? 'laptop' : 'bed'
  const item = interactables.find(i => i.id === id)
  if (item?.seat) return { x: item.seat.x, z: item.seat.z, yaw: item.seat.yaw }
  const geom = getHouseTierGeometry(tier)
  return type === 'desk'
    ? { x: geom.desk.x, z: geom.desk.z, yaw: geom.desk.yaw }
    : { x: geom.bed.x,  z: geom.bed.z,  yaw: 0 }
}

export class InteriorManager {
  private app: Application
  private input: InputManager
  private canvas: HTMLCanvasElement
  private loader: AssetLoader
  private factory: BuildingFactory

  private interiorRoot: pc.Entity | null = null
  private scene: InteriorScene | null = null
  private player: PlayerController | null = null
  private camera: InteriorCamera
  private ui: InteriorUI
  private interaction: InteractionLoop
  private door: DoorTrigger
  private transition: SceneTransition

  private collisionBoxes: CollisionBox[] = []
  private currentMember: string | null = null
  private currentHouseOwnerId: string | null = null
  private currentHouseTier = 1

  // Multiplayer — visitor identity (the authenticated user visiting the house)
  private visitorId: string | null = null
  private visitorName: string | null = null
  private visitorCharacterModel: string | null = null
  private syncAdapter = new PlayerSyncAdapter()
  private remotePlayers = new Map<string, NetworkedPlayer>()

  // Owner NPC driven by OrgRoomState (Phase 8). `ownerNpcGen` is bumped on
  // every spawn/despawn request — in-flight spawns compare their captured gen
  // against the current value and abort if superseded, preventing leaks when
  // a despawn arrives mid-spawn.
  private ownerNpc: NetworkedPlayer | null = null
  private ownerNpcGen = 0
  private orgRoomUnsubscribe: (() => void) | null = null

  /** Called when user triggers exit (door, ESC, or button). Set by GardenEngine. */
  onExit: (() => void) | null = null

  constructor(
    app: Application,
    input: InputManager,
    materials: MaterialFactory,
    canvas: HTMLCanvasElement,
    container: HTMLElement,
  ) {
    this.app = app
    this.input = input
    this.canvas = canvas
    this.loader = new AssetLoader(app.app)
    this.factory = new BuildingFactory(this.loader, materials)

    this.camera = new InteriorCamera()
    this.ui = new InteriorUI()
    this.interaction = new InteractionLoop()
    this.door = new DoorTrigger()
    this.transition = new SceneTransition()

    this.ui.init(container)
    this.ui.hide()
    this.ui.onExitClick = () => this.onExit?.()
    this.transition.init(container)

    // Door trigger — interior exit only (entry is via garden click)
    this.door.setScene('interior')
    this.door.onExit(() => this.onExit?.())
  }

  /**
   * Build (or rebuild) the interior scene for a specific house tier.
   * Destroys previous interior children and creates fresh layout.
   */
  async buildForTier(tier: number): Promise<void> {
    if (!this.interiorRoot) {
      this.interiorRoot = new pc.Entity('InteriorRoot')
      this.interiorRoot.enabled = false
      this.app.root.addChild(this.interiorRoot)
    }

    // Destroy old interior children (snapshot to avoid mutation during iteration)
    const oldChildren = [...this.interiorRoot.children] as pc.Entity[]
    for (const child of oldChildren) child.destroy()

    this.scene = new InteriorScene(this.factory)
    this.collisionBoxes = await this.scene.build(this.interiorRoot, tier)

    // Wire interactable actions
    for (const item of this.scene.items) {
      item.onUse(() => {
        const { seat } = item
        if (item.action === 'sit' && seat) this.player?.sitAt(seat.x, seat.z, seat.yaw, seat.y)
        if (item.action === 'sleep' && seat) this.player?.sleepAt(seat.x, seat.z, seat.yaw, seat.y)
        this.ui.showInfo(item.infoText)
        this.interaction.setActiveSeat(item.id)
        if (item.id === 'tv') this.scene?.tvEffect.turnOn()
      })
    }

    // Interior built — ready for interaction
  }

  /**
   * Enter a house interior.
   * Called during SceneTransition.perform() black frame.
   */
  /** Identity of a user visiting a house (used for multiplayer presence). */
  // Visitor type defined inline in enter() signature

  /**
   * Enter a house interior.
   * @param house - The house to enter (may or may not belong to the visitor)
   * @param visitor - The authenticated user entering the house. Their identity is
   *   broadcast to the multiplayer room so OTHER clients in the same house see them.
   *   If omitted (e.g., unauthenticated/dev mode), falls back to house owner identity.
   */
  async enter(
    house: HouseResult,
    visitor?: { userId: string; name: string; characterModel: string | null } | null,
  ): Promise<void> {
    await this.buildForTier(house.tier)

    // Set door exit trigger for this tier's room size
    const { ROOM_SIZE_BY_TIER } = await import('../housetest/SceneConfig')
    const room = ROOM_SIZE_BY_TIER[house.tier] ?? ROOM_SIZE_BY_TIER[0]
    this.door.setDoorPosition(room.doorIndex + 0.5, room.depth)

    this.currentMember = house.memberName
    this.currentHouseOwnerId = house.memberId
    this.currentHouseTier = house.tier

    // Store visitor identity for multiplayer broadcast
    this.visitorId = visitor?.userId ?? house.memberId
    this.visitorName = visitor?.name ?? house.memberName
    this.visitorCharacterModel = visitor?.characterModel ?? house.characterModel

    // Enable interior root
    this.interiorRoot!.enabled = true

    // Spawn player with the visitor's character model (keeps identity when visiting others' houses)
    this.player = new PlayerController(this.loader, this.input)
    // Spawn X is the room centre so the player lands clear of the back wall
    // regardless of tier width. Z is a fixed small offset from the back wall.
    const playerEnterX = getHouseTierGeometry(this.currentHouseTier).width / 2
    await this.player.init(this.interiorRoot!, playerEnterX, PLAYER_ENTER_Z, this.visitorCharacterModel)
    this.player.setCollisionBoxes(this.collisionBoxes)

    // Switch to interior camera
    this.camera.enable(this.app.camera, this.canvas)

    // Show UI
    this.ui.show(house.memberName)
    this.interaction.reset()
    this.syncAdapter.reset()

    // Join multiplayer room keyed by HOUSE OWNER (so visitors + owner meet in same room)
    this.joinMultiplayerRoom(house.memberId)

    // Spawn the house owner as an interior NPC if OrgRoomState says they're
    // currently at home. Only shows someone else's owner — if the visitor IS
    // the owner, they're already represented as the player character.
    if (house.memberId !== this.visitorId) {
      await this.refreshOwnerNpc(house.memberId)
      this.orgRoomUnsubscribe = OrgRoomClient.getInstance().addMemberChangeListener(
        (userId, snapshot) => {
          if (userId !== this.currentHouseOwnerId) return
          void this.onOwnerStateChanged(snapshot)
        },
      )
    }
  }

  /** Per-frame update while in interior mode. */
  update(dt: number): void {
    if (!this.player || !this.scene) return

    const camYaw = this.camera.yaw
    this.player.update(dt, camYaw)

    const playerPos = this.player.getPosition()
    this.camera.update(playerPos)
    this.door.update(playerPos)
    this.interaction.update(this.player, this.input, this.scene, this.ui)
    this.interaction.updateTV(dt, this.scene)

    // Multiplayer: sync local position + interpolate remote players
    const animState = this.player.isSitting ? 'sit' : this.player.isSleeping ? 'sleep' : 'idle'
    this.syncAdapter.update(dt, playerPos.x, playerPos.z, camYaw, animState, ColyseusClient.getInstance())
    for (const remote of this.remotePlayers.values()) {
      remote.update()
    }
    // Interior owner NPC (Phase 8) — driven by OrgRoomState, interpolated here.
    this.ownerNpc?.update()

    // ESC key — exit
    if (this.input.isPressed(pc.KEY_ESCAPE)) {
      this.onExit?.()
    }
  }

  /** Get the fade transition (used by GardenEngine for enter/exit coordination). */
  get sceneTransition(): SceneTransition { return this.transition }

  /** Exit the interior — called during SceneTransition.perform() black frame. */
  exit(): void {
    // Clean up player state
    if (this.player?.isSitting) this.player.standUp()
    if (this.player?.isSleeping) this.player.wakeUp()
    this.scene?.tvEffect.turnOff()

    // Unsubscribe from OrgRoom owner state updates
    if (this.orgRoomUnsubscribe) {
      this.orgRoomUnsubscribe()
      this.orgRoomUnsubscribe = null
    }
    // Bump gen to invalidate any in-flight owner NPC spawn still awaiting assets
    this.ownerNpcGen++
    this.ownerNpc?.despawn()
    this.ownerNpc = null

    // Disable camera + UI
    this.camera.disable()
    this.ui.hide()

    // Leave multiplayer room + despawn remote players
    this.leaveMultiplayerRoom()

    // Destroy player
    this.player?.destroy()
    this.player = null

    // Hide interior root (keep built for reuse)
    if (this.interiorRoot) this.interiorRoot.enabled = false

    this.interaction.reset()
    this.syncAdapter.reset()
    this.currentMember = null
    this.currentHouseOwnerId = null
    this.visitorId = null
    this.visitorName = null
    this.visitorCharacterModel = null
  }

  get isActive(): boolean { return this.interiorRoot?.enabled ?? false }
  get memberName(): string | null { return this.currentMember }

  destroy(): void {
    this.exit()
    this.camera.destroy()
    this.ui.destroy()
    this.door.destroy()
    this.transition.destroy()
    this.interiorRoot?.destroy()
    this.interiorRoot = null
    this.scene = null
  }

  // ─── Multiplayer helpers ───────────────────────

  /**
   * Join the Colyseus house room keyed by the HOUSE OWNER's memberId.
   * The visitor's own identity (not the house owner's) is sent as the player data
   * so other clients in the room can distinguish and render this specific user.
   */
  private joinMultiplayerRoom(houseOwnerId: string): void {
    const client = ColyseusClient.getInstance()
    client.setCallbacks({
      onPlayerJoin: (sessionId, player) => this.spawnRemotePlayer(sessionId, player),
      onPlayerLeave: (sessionId) => this.despawnRemotePlayer(sessionId),
      onPlayerMove: (sessionId, player) => {
        this.remotePlayers.get(sessionId)?.setTarget(player)
      },
    })
    // Non-blocking — multiplayer is optional (game works offline)
    client.joinHouseRoom(houseOwnerId, {
      userId: this.visitorId ?? houseOwnerId,
      name: this.visitorName ?? 'Visitor',
      characterModel: this.visitorCharacterModel ?? '',
    }).catch((err) => {
      console.warn('[InteriorManager] Multiplayer unavailable:', err)
    })
  }

  private leaveMultiplayerRoom(): void {
    for (const remote of this.remotePlayers.values()) {
      remote.despawn()
    }
    this.remotePlayers.clear()
    ColyseusClient.getInstance().leaveRoom().catch(() => {
      // Room may already be disconnected — safe to ignore
    })
  }

  private async spawnRemotePlayer(sessionId: string, player: PlayerData): Promise<void> {
    if (!this.interiorRoot || this.remotePlayers.has(sessionId)) return
    const remote = new NetworkedPlayer(sessionId, player.name)
    await remote.spawn(this.interiorRoot, this.loader, player)
    this.remotePlayers.set(sessionId, remote)
  }

  private despawnRemotePlayer(sessionId: string): void {
    const remote = this.remotePlayers.get(sessionId)
    if (remote) {
      remote.despawn()
      this.remotePlayers.delete(sessionId)
    }
  }

  // ─── Owner NPC (Phase 8) ────────────────────

  /**
   * Decide whether the house owner should be visible inside, and which seat
   * they should occupy, based on their current OrgRoomState.
   */
  private ownerSeatForSnapshot(
    ownerId: string,
    snapshot: MemberStateSnapshot,
  ): { x: number; z: number; yaw: number } | null {
    // The server sets locationContext to `house_{ownerId}` when the member
    // is placed at their own desk/bed. Any other context (garden, break_*,
    // tree_*) means they're not currently inside the house.
    if (snapshot.locationContext !== `house_${ownerId}`) return null
    // Presence dictates the pose: at_home → bed, active → desk.
    // Seat position is tier-specific (3×3 hut vs 4×4 cottage vs 5×5 mansion).
    const type = snapshot.presence === 'at_home' ? 'bed' : 'desk'
    return getOwnerSeat(this.currentHouseTier, type)
  }

  /** Spawn (or respawn) the owner NPC based on current OrgRoomState. */
  private async refreshOwnerNpc(ownerId: string): Promise<void> {
    if (!this.interiorRoot) return
    const snapshot = OrgRoomClient.getInstance().getMember(ownerId)
    if (!snapshot) return

    const seat = this.ownerSeatForSnapshot(ownerId, snapshot)
    if (!seat) {
      // Owner is elsewhere — ensure no stale NPC remains and cancel any
      // in-flight spawn by bumping the generation.
      this.ownerNpcGen++
      this.ownerNpc?.despawn()
      this.ownerNpc = null
      return
    }

    // Already spawned — just reposition to match any seat change.
    if (this.ownerNpc) {
      this.ownerNpc.setTarget({
        userId: ownerId,
        name: snapshot.name,
        characterModel: snapshot.characterModel,
        x: seat.x,
        z: seat.z,
        yaw: seat.yaw,
        animState: snapshot.presence === 'at_home' ? 'sleep' : 'sit',
      })
      return
    }

    // Fresh spawn — capture the current generation so a concurrent despawn
    // (exit, owner leaving, rapid state flip) can invalidate this call.
    const myGen = ++this.ownerNpcGen
    const candidate = new NetworkedPlayer(`owner_${ownerId}`, snapshot.name)
    await candidate.spawn(this.interiorRoot, this.loader, {
      userId: ownerId,
      name: snapshot.name,
      characterModel: snapshot.characterModel,
      x: seat.x,
      z: seat.z,
      yaw: seat.yaw,
      animState: snapshot.presence === 'at_home' ? 'sleep' : 'sit',
    })

    // If anything superseded us (despawn, exit, re-entry), discard the candidate.
    if (this.ownerNpcGen !== myGen || !this.interiorRoot?.enabled) {
      candidate.despawn()
      return
    }
    this.ownerNpc = candidate
  }

  /** Handle an OrgRoom member-change event for the current house owner. */
  private async onOwnerStateChanged(snapshot: MemberStateSnapshot | null): Promise<void> {
    if (!this.currentHouseOwnerId) return
    if (!snapshot) {
      // Owner was removed from the org — despawn.
      this.ownerNpc?.despawn()
      this.ownerNpc = null
      return
    }
    await this.refreshOwnerNpc(this.currentHouseOwnerId)
  }
}
