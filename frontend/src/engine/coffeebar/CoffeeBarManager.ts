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
 * CoffeeBarManager — coordinator for the coffee bar interior mode.
 *
 * Lifecycle: init once → enter(visitor) → update(dt) per frame → exit() → destroy()
 *
 * Delegates to:
 *   CoffeeBarScene       — room geometry (floor, walls, bar, machine)
 *   PlayerController     — WASD movement + locomotion animations (shared
 *                          with house interiors; KayKit-compatible)
 *   InteriorCamera       — orbit camera (reused directly; same PBR pipeline)
 *   CoffeeBarUI          — DOM overlays (header, prompt, exit)
 *   CoffeeBarRoomClient  — Colyseus subscription for queue / active state
 *   SceneTransition      — fade-to-black overlay (reused)
 *
 * The coffee bar is a singleton — built once on first entry, hidden on exit,
 * re-enabled on the next entry. Matches the InteriorManager pattern so the
 * enter/exit transitions share the same fade and camera-swap choreography.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { InputManager } from '../input/InputManager'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { AssetLoader } from '../assets/AssetLoader'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { InteriorCamera } from '../interior/InteriorCamera'
import { SceneTransition } from '../housetest/SceneTransition'
import { PlayerController } from '../housetest/PlayerController'
import { DoorTrigger } from '../housetest/DoorTrigger'
import type { CollisionBox } from '../housetest/CollisionSystem'
import { CoffeeBarScene } from './CoffeeBarScene'
import { CoffeeBarUI } from './CoffeeBarUI'
import { CoffeeBarRoomClient } from './CoffeeBarRoomClient'
import { CoffeeBarInteractionLoop } from './CoffeeBarInteractionLoop'
import { CoffeeBarRemotePlayers } from './CoffeeBarRemotePlayers'
import { CoffeeBarBrewVisual } from './CoffeeBarBrewVisual'
import { LabelRenderer } from '../rendering/LabelRenderer'
import { COFFEE_SPAWN, COFFEE_ROOM } from './SceneConfig'

/** Spoken lines after taking a drink — picked at random for flavour. */
const DRINK_LINES = [
  'Mmm, perfect.',
  'Just what I needed.',
  'Ahhh.',
  'That hits the spot.',
  'Smooth.',
]
/** ms — how long the speech bubble stays up + how long the UseItem anim plays.
 *  Sized to comfortably contain one full cycle of the Use_Item track at the
 *  0.4× playback speed configured in PlayerController. */
const DRINK_REACTION_MS = 3500

/** Broadcast the local position at 20Hz — matches OrgRoom / CoffeeBarRoom cadence. */
const MOVE_BROADCAST_INTERVAL = 0.05

export interface CoffeeBarVisitor {
  userId: string
  name: string
  characterModel: string | null
  orgId: string
}

export class CoffeeBarManager {
  private app: Application
  private input: InputManager
  private canvas: HTMLCanvasElement
  private loader: AssetLoader
  private factory: BuildingFactory

  private root: pc.Entity | null = null
  private scene: CoffeeBarScene | null = null
  private player: PlayerController | null = null
  private camera: InteriorCamera
  private ui: CoffeeBarUI
  private transition: SceneTransition
  private roomClient: CoffeeBarRoomClient
  private interaction: CoffeeBarInteractionLoop
  private door: DoorTrigger

  private collisionBoxes: CollisionBox[] = []
  private localUserId: string = ''
  private remotePlayers: CoffeeBarRemotePlayers | null = null
  private moveBroadcastAccum = 0

  private brewVisual: CoffeeBarBrewVisual | null = null
  private speechBubble: pc.Entity | null = null
  private speechHideAtMs = 0
  private drinkAnimEndMs = 0

  /** Called when the user triggers exit (button or ESC). Set by GardenEngine. */
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
    this.ui = new CoffeeBarUI()
    this.transition = new SceneTransition()
    this.roomClient = new CoffeeBarRoomClient()
    this.interaction = new CoffeeBarInteractionLoop()
    this.door = new DoorTrigger()

    this.ui.init(container)
    this.ui.hide()
    this.ui.onExitClick = () => this.onExit?.()
    this.ui.onDrinkSelect = (drinkId) => {
      this.interaction.closeMenu()
      this.roomClient.enqueueDrink(drinkId)
    }
    this.ui.onMenuCancel = () => this.interaction.closeMenu()
    this.interaction.onDrinkTaken = () => this.onLocalDrinkTaken()
    this.transition.init(container)

    // Interior door — walking out of the front door triggers exit. Same
    // mechanism the house interior uses (housetest/DoorTrigger).
    this.door.setScene('interior')
    this.door.setDoorPosition(COFFEE_ROOM.doorIndex + 0.5, COFFEE_ROOM.depth)
    this.door.onExit(() => this.onExit?.())
  }

  /** Build (or rebuild) the interior geometry. Idempotent via destroyChildren. */
  async build(): Promise<void> {
    if (!this.root) {
      this.root = new pc.Entity('CoffeeBarRoot')
      this.root.enabled = false
      this.app.root.addChild(this.root)
    }

    const oldChildren = [...this.root.children] as pc.Entity[]
    for (const child of oldChildren) child.destroy()

    this.scene = new CoffeeBarScene(this.factory)
    this.collisionBoxes = await this.scene.build(this.root, this.app)

    this.brewVisual = new CoffeeBarBrewVisual(this.factory)
    this.brewVisual.attach(this.root)
  }

  /**
   * Enter the coffee bar. Called during SceneTransition.perform() black frame.
   * Joins the shared Colyseus room, spawns the local player, enables the
   * interior camera and UI.
   */
  async enter(visitor: CoffeeBarVisitor): Promise<void> {
    await this.build()

    this.root!.enabled = true
    this.localUserId = visitor.userId
    this.interaction.reset()

    this.player = new PlayerController(this.loader, this.input)
    await this.player.init(this.root!, COFFEE_SPAWN.x, COFFEE_SPAWN.z, visitor.characterModel)
    this.player.setCollisionBoxes(this.collisionBoxes)

    this.camera.enable(this.app.camera, this.canvas)
    this.ui.show()

    // Remote-player rendering — spawns/updates/despawns visitors other than
    // the local player based on CoffeeBarRoom state.
    this.remotePlayers = new CoffeeBarRemotePlayers(
      this.root!, this.loader, this.roomClient, this.localUserId,
    )
    this.moveBroadcastAccum = 0

    // Non-blocking — the scene works offline if the multiplayer server is down.
    this.roomClient
      .connect(visitor.orgId, {
        userId: visitor.userId,
        name: visitor.name,
        characterModel: visitor.characterModel ?? '',
      })
      .catch((err) => console.warn('[CoffeeBarManager] Multiplayer unavailable:', err))
  }

  /** Per-frame update while in the coffee bar. */
  update(dt: number): void {
    if (!this.player || !this.scene) return
    const camYaw = this.camera.yaw
    this.player.update(dt, camYaw)

    const playerPos = this.player.getPosition()
    this.camera.update(playerPos)
    this.door.update(playerPos)

    this.broadcastMove(dt, playerPos)
    this.remotePlayers?.update()

    this.interaction.update(this.player, this.input, this.ui, this.roomClient, this.localUserId)
    if (this.interaction.isMenuOpen) {
      this.ui.showMenu()
    } else {
      this.ui.hideMenu()
    }

    const nowMs = Date.now()
    this.brewVisual?.update(this.roomClient.snapshot, nowMs)
    this.tickDrinkReaction(nowMs)

    // ESC — close menu if open, otherwise exit the bar.
    if (this.input.isPressed(pc.KEY_ESCAPE)) {
      if (this.interaction.isMenuOpen) {
        this.interaction.closeMenu()
      } else {
        this.onExit?.()
      }
    }
  }

  /**
   * Broadcast the local player's position/pose at 20Hz. Throttled via a
   * simple accumulator so we don't blast the server at render framerate.
   */
  private broadcastMove(dt: number, pos: pc.Vec3): void {
    this.moveBroadcastAccum += dt
    if (this.moveBroadcastAccum < MOVE_BROADCAST_INTERVAL) return
    this.moveBroadcastAccum = 0

    const entity = this.player?.getEntity()
    if (!entity) return

    const yaw = entity.getEulerAngles().y
    const move = this.input.getMovementVector()
    const animState = move.x !== 0 || move.z !== 0 ? 'walk' : 'idle'
    this.roomClient.sendMove(pos.x, pos.z, yaw, animState)
  }

  /**
   * Triggered by CoffeeBarInteractionLoop when the local user picks up
   * their dispensed drink. Drives the Use_Item animation and floats a
   * speech bubble above the player for DRINK_REACTION_MS.
   *
   * Why `working=2` and not `playAnimation('UseItem')`?  The shared
   * LOCOMOTION_STATE_GRAPH gates UseItem on the integer `working` parameter:
   * `Idle → UseItem` when working==2, `UseItem → Idle` when working==0.
   * Calling `transition('UseItem')` directly enters the state but the
   * `working==0` condition immediately bounces it back to Idle, so the
   * animation never visibly plays. Setting the parameter holds the state.
   *
   * Note: KayKit's pack has no dedicated drink track — `Use_Item` is the
   * closest "raise object" gesture. A true cup-to-mouth motion would need
   * a custom GLB.
   */
  private onLocalDrinkTaken(): void {
    if (!this.player) return
    const entity = this.player.getEntity()
    const anim = entity?.anim
    try { anim?.setInteger('working', 2) }
    catch (e) { if (import.meta.env.DEV) console.debug('[CoffeeBar] set working=2:', e) }
    this.drinkAnimEndMs = Date.now() + DRINK_REACTION_MS

    if (!entity) return

    // Clear any previous bubble so rapid successive drinks don't stack.
    this.speechBubble?.destroy()
    const line = DRINK_LINES[Math.floor(Math.random() * DRINK_LINES.length)]
    const bubble = LabelRenderer.create(this.app, line, {
      fontSize: 32,
      bgColor: 'rgba(255,255,255,0.92)',
      textColor: '#1f1813',
    })
    bubble.setLocalPosition(0, 2.0, 0)
    entity.addChild(bubble)
    this.speechBubble = bubble
    this.speechHideAtMs = Date.now() + DRINK_REACTION_MS
  }

  /** Tear down the speech bubble + return player to Idle when timers expire. */
  private tickDrinkReaction(nowMs: number): void {
    if (this.speechBubble && nowMs >= this.speechHideAtMs) {
      this.speechBubble.destroy()
      this.speechBubble = null
    }
    if (this.drinkAnimEndMs !== 0 && nowMs >= this.drinkAnimEndMs) {
      this.drinkAnimEndMs = 0
      const anim = this.player?.getEntity()?.anim
      try { anim?.setInteger('working', 0) }
      catch (e) { if (import.meta.env.DEV) console.debug('[CoffeeBar] set working=0:', e) }
    }
  }

  /** Exit the coffee bar. Called during SceneTransition.perform() black frame. */
  exit(): void {
    // Drop the local player from the queue before disconnecting so others
    // don't see a phantom entry.
    this.roomClient.leaveQueue()
    this.interaction.reset()

    this.camera.disable()
    this.ui.hide()

    this.remotePlayers?.destroy()
    this.remotePlayers = null

    // Fire-and-forget; we don't block the exit fade on the socket close.
    this.roomClient.disconnect().catch(() => {
      // Already disconnected — safe to ignore
    })

    this.speechBubble?.destroy()
    this.speechBubble = null
    this.drinkAnimEndMs = 0

    this.player?.destroy()
    this.player = null

    if (this.root) this.root.enabled = false
    this.localUserId = ''
  }

  get sceneTransition(): SceneTransition { return this.transition }
  get isActive(): boolean { return this.root?.enabled ?? false }

  destroy(): void {
    this.exit()
    this.camera.destroy()
    this.ui.destroy()
    this.door.destroy()
    this.transition.destroy()
    this.root?.destroy()
    this.root = null
    this.scene = null
  }
}
