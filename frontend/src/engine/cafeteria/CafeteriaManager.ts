// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CafeteriaManager — coordinator for the cafeteria interior mode.
 *
 * Lifecycle: init once → enter(visitor) → update(dt) per frame → exit() → destroy()
 *
 * Delegates to the same generic subsystems as CoffeeBarManager:
 *   InteriorCamera       — orbit camera
 *   SceneTransition      — fade-to-black overlay
 *   PlayerController     — WASD + KayKit locomotion (shared with houses + coffee bar)
 *   DoorTrigger          — proximity exit detection
 * Plus cafeteria-specific pieces:
 *   CafeteriaScene       — loads the cafeteria GLB at origin
 *   CafeteriaUI          — DOM overlay with meal menu
 *   CafeteriaRoomClient  — Colyseus CafeteriaRoom subscription
 *   CafeteriaInteractionLoop — proximity + E-key state machine
 *   CafeteriaRemotePlayers   — spawns/updates/despawns other visitors
 *
 * The cafeteria is a singleton — built once on first entry, disabled on
 * exit, re-enabled on next entry. Matches the coffee bar lifecycle so both
 * interiors share the same enter/exit choreography with GardenEngine.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { InputManager } from '../input/InputManager'
import { AssetLoader } from '../assets/AssetLoader'
import { InteriorCamera } from '../interior/InteriorCamera'
import { SceneTransition } from '../housetest/SceneTransition'
import { PlayerController } from '../housetest/PlayerController'
import { DoorTrigger } from '../housetest/DoorTrigger'
import type { CollisionBox } from '../housetest/CollisionSystem'
import { CafeteriaScene } from './CafeteriaScene'
import { CafeteriaUI } from './CafeteriaUI'
import { CafeteriaRoomClient } from './CafeteriaRoomClient'
import { CafeteriaInteractionLoop } from './CafeteriaInteractionLoop'
import { CafeteriaRemotePlayers } from './CafeteriaRemotePlayers'
import { LabelRenderer } from '../rendering/LabelRenderer'
import { CAFETERIA_SPAWN, EXIT_DOOR_POS } from './SceneConfig'

/** Spoken lines after taking a meal — picked at random for flavour. */
const FOOD_LINES = [
  'Delicious.',
  'Hit the spot.',
  'So good.',
  'That was great.',
  'Mmm.',
]

/** ms — speech bubble duration + Use_Item animation hold time. Same as
 *  coffee bar's drink reaction; sized for one cycle of Use_Item at 0.4×. */
const EAT_REACTION_MS = 3500

/** Broadcast the local position at 20Hz — matches OrgRoom / CafeteriaRoom cadence. */
const MOVE_BROADCAST_INTERVAL = 0.05

export interface CafeteriaVisitor {
  userId: string
  name: string
  characterModel: string | null
  orgId: string
}

export class CafeteriaManager {
  private app: Application
  private input: InputManager
  private canvas: HTMLCanvasElement
  private loader: AssetLoader

  private root: pc.Entity | null = null
  private scene: CafeteriaScene | null = null
  private player: PlayerController | null = null
  private camera: InteriorCamera
  private ui: CafeteriaUI
  private transition: SceneTransition
  private roomClient: CafeteriaRoomClient
  private interaction: CafeteriaInteractionLoop
  private door: DoorTrigger

  private collisionBoxes: CollisionBox[] = []
  private localUserId: string = ''
  private remotePlayers: CafeteriaRemotePlayers | null = null
  private moveBroadcastAccum = 0

  private speechBubble: pc.Entity | null = null
  private speechHideAtMs = 0
  private eatAnimEndMs = 0

  /** Called when the user triggers exit. Set by GardenEngine. */
  onExit: (() => void) | null = null

  constructor(
    app: Application,
    input: InputManager,
    canvas: HTMLCanvasElement,
    container: HTMLElement,
  ) {
    this.app = app
    this.input = input
    this.canvas = canvas
    this.loader = new AssetLoader(app.app)

    this.camera = new InteriorCamera()
    this.ui = new CafeteriaUI()
    this.transition = new SceneTransition()
    this.roomClient = new CafeteriaRoomClient()
    this.interaction = new CafeteriaInteractionLoop()
    this.door = new DoorTrigger()

    this.ui.init(container)
    this.ui.hide()
    this.ui.onExitClick = () => this.onExit?.()
    this.ui.onMealSelect = (mealId) => {
      this.interaction.closeMenu()
      this.roomClient.enqueueMeal(mealId)
    }
    this.ui.onMenuCancel = () => this.interaction.closeMenu()
    this.interaction.onMealTaken = () => this.onLocalMealTaken()
    this.transition.init(container)

    // Interior door — walking through the front door triggers exit.
    this.door.setScene('interior')
    this.door.setDoorPosition(EXIT_DOOR_POS.x, EXIT_DOOR_POS.z)
    this.door.onExit(() => this.onExit?.())
  }

  /** Build (or rebuild) the interior geometry. Idempotent via destroyChildren. */
  async build(): Promise<void> {
    if (!this.root) {
      this.root = new pc.Entity('CafeteriaRoot')
      this.root.enabled = false
      this.app.root.addChild(this.root)
    }

    const oldChildren = [...this.root.children] as pc.Entity[]
    for (const child of oldChildren) child.destroy()

    this.scene = new CafeteriaScene(this.loader)
    this.collisionBoxes = await this.scene.build(this.root, this.app)
  }

  /** Enter the cafeteria. Called during SceneTransition.perform() black frame. */
  async enter(visitor: CafeteriaVisitor): Promise<void> {
    await this.build()

    this.root!.enabled = true
    this.localUserId = visitor.userId
    this.interaction.reset()

    this.player = new PlayerController(this.loader, this.input)
    await this.player.init(this.root!, CAFETERIA_SPAWN.x, CAFETERIA_SPAWN.z, visitor.characterModel)
    this.player.setCollisionBoxes(this.collisionBoxes)

    this.camera.enable(this.app.camera, this.canvas)
    this.ui.show()

    this.remotePlayers = new CafeteriaRemotePlayers(
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
      .catch((err) => console.warn('[CafeteriaManager] Multiplayer unavailable:', err))
  }

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
    this.tickEatReaction(nowMs)

    if (this.input.isPressed(pc.KEY_ESCAPE)) {
      if (this.interaction.isMenuOpen) {
        this.interaction.closeMenu()
      } else {
        this.onExit?.()
      }
    }
  }

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
   * Fires when the local user picks up their dispensed meal. Drives the
   * Use_Item animation and floats a speech bubble above the player.
   *
   * Reuses `working=2` from the coffee bar drink reaction — the shared
   * LOCOMOTION_STATE_GRAPH gates UseItem on the integer param. KayKit has
   * no dedicated eating track; Use_Item reads as a "raise object to face"
   * gesture that works for both drinking and eating.
   */
  private onLocalMealTaken(): void {
    if (!this.player) return
    const entity = this.player.getEntity()
    const anim = entity?.anim
    try { anim?.setInteger('working', 2) }
    catch (e) { if (import.meta.env.DEV) console.debug('[Cafeteria] set working=2:', e) }
    this.eatAnimEndMs = Date.now() + EAT_REACTION_MS

    if (!entity) return

    this.speechBubble?.destroy()
    const line = FOOD_LINES[Math.floor(Math.random() * FOOD_LINES.length)]
    const bubble = LabelRenderer.create(this.app, line, {
      fontSize: 32,
      bgColor: 'rgba(255,255,255,0.92)',
      textColor: '#1f3010',
    })
    bubble.setLocalPosition(0, 2.0, 0)
    entity.addChild(bubble)
    this.speechBubble = bubble
    this.speechHideAtMs = Date.now() + EAT_REACTION_MS
  }

  private tickEatReaction(nowMs: number): void {
    if (this.speechBubble && nowMs >= this.speechHideAtMs) {
      this.speechBubble.destroy()
      this.speechBubble = null
    }
    if (this.eatAnimEndMs !== 0 && nowMs >= this.eatAnimEndMs) {
      this.eatAnimEndMs = 0
      const anim = this.player?.getEntity()?.anim
      try { anim?.setInteger('working', 0) }
      catch (e) { if (import.meta.env.DEV) console.debug('[Cafeteria] set working=0:', e) }
    }
  }

  exit(): void {
    this.roomClient.leaveQueue()
    this.interaction.reset()

    this.camera.disable()
    this.ui.hide()

    this.remotePlayers?.destroy()
    this.remotePlayers = null

    this.roomClient.disconnect().catch(() => {
      // Already disconnected — safe to ignore
    })

    this.speechBubble?.destroy()
    this.speechBubble = null
    this.eatAnimEndMs = 0

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
