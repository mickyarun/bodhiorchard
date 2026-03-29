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
import { ColyseusClient, NetworkedPlayer, PlayerSyncAdapter, type PlayerData } from '../../multiplayer'

// Player spawn inside the room — clear of all furniture collision boxes
const PLAYER_ENTER_X = 2.0
const PLAYER_ENTER_Z = 1.5

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
  private built = false
  private currentMember: string | null = null

  // Multiplayer
  private syncAdapter = new PlayerSyncAdapter()
  private remotePlayers = new Map<string, NetworkedPlayer>()

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

  /** Build the interior scene (called once, reused for every house). */
  async build(): Promise<void> {
    if (this.built) return
    this.interiorRoot = new pc.Entity('InteriorRoot')
    this.interiorRoot.enabled = false
    this.app.root.addChild(this.interiorRoot)

    this.scene = new InteriorScene(this.factory)
    this.collisionBoxes = await this.scene.build(this.interiorRoot)

    // Wire interactable actions
    for (const item of this.scene.items) {
      item.onUse(() => {
        const { seat } = item
        if (item.action === 'sit' && seat) this.player?.sitAt(seat.x, seat.z, seat.yaw)
        if (item.action === 'sleep' && seat) this.player?.sleepAt(seat.x, seat.z, seat.yaw)
        this.ui.showInfo(item.infoText)
        this.interaction.setActiveSeat(item.id)
        if (item.id === 'tv') this.scene?.tvEffect.turnOn()
      })
    }

    this.built = true
  }

  /**
   * Enter a house interior.
   * Called during SceneTransition.perform() black frame.
   */
  async enter(house: HouseResult): Promise<void> {
    if (!this.built) await this.build()
    this.currentMember = house.memberName
    // memberId used by multiplayer room join below

    // Enable interior root
    this.interiorRoot!.enabled = true

    // Spawn player
    this.player = new PlayerController(this.loader, this.input)
    await this.player.init(this.interiorRoot!, PLAYER_ENTER_X, PLAYER_ENTER_Z)
    this.player.setCollisionBoxes(this.collisionBoxes)

    // Switch to interior camera
    this.camera.enable(this.app.camera, this.canvas)

    // Show UI
    this.ui.show(house.memberName)
    this.interaction.reset()
    this.syncAdapter.reset()

    // Join multiplayer room (non-blocking — game works without server)
    this.joinMultiplayerRoom(house.memberId)
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
    this.built = false
  }

  // ─── Multiplayer helpers ───────────────────────

  private joinMultiplayerRoom(memberId: string): void {
    const client = ColyseusClient.getInstance()
    client.setCallbacks({
      onPlayerJoin: (sessionId, player) => this.spawnRemotePlayer(sessionId, player),
      onPlayerLeave: (sessionId) => this.despawnRemotePlayer(sessionId),
      onPlayerMove: (sessionId, player) => {
        this.remotePlayers.get(sessionId)?.setTarget(player)
      },
    })
    // Non-blocking — multiplayer is optional (game works offline)
    client.joinHouseRoom(memberId, {
      userId: memberId,  // TODO: use actual user ID from auth
      name: this.currentMember || 'Visitor',
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
    await remote.spawn(this.interiorRoot, this.loader, this.app, player)
    this.remotePlayers.set(sessionId, remote)
  }

  private despawnRemotePlayer(sessionId: string): void {
    const remote = this.remotePlayers.get(sessionId)
    if (remote) {
      remote.despawn()
      this.remotePlayers.delete(sessionId)
    }
  }
}
