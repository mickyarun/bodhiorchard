// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * AgentCharacter — animated robot agent with wandering behavior.
 *
 * Lifecycle: spawn (spin+beam) → work (idle/grab cycle) → walk between trees → complete (jump+beam) → destroy
 *
 * Uses robot.glb animations: iddle, grab, attackspin, jump, walking, walkstart, walkingstop
 * Follows GardenBirdSystem-style state machine for wandering between repo trees.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { Application } from '../core/Application'
import { AGENT_ROBOT } from '../assets/AssetManifest'
import { AgentLabel } from './AgentLabel'
import { SpaceshipTransport } from './SpaceshipTransport'
import { getNextPhrase } from './AgentWorkingPhrases'
import { getSkillDisplayName } from '@shared/agents/AgentPhrases'
import { setTreeData } from '../world/TreeNodeData'

const ROBOT_SCALE = 0.15
const WALK_SPEED = 1.5          // units/sec (slower, more deliberate)
const ARRIVE_DIST_SQ = 2.25    // 1.5^2 — squared distance for arrival check
const WORK_DURATION_MIN = 6     // seconds at each tree (longer stay)
const WORK_DURATION_MAX = 12
const PHRASE_INTERVAL = 4       // seconds between label text changes
const SPAWN_ANIM_MS = 2500      // longer spawn animation
const COMPLETE_PAUSE_MS = 2000
const TELEPORT_MS = 1200        // slower teleport beam
const LABEL_Y_OVERRIDE = 1.8   // fixed label height above ground (measured height unreliable)
const HOP_INTERVAL_MIN = 3     // seconds between hops while walking
const HOP_INTERVAL_MAX = 5
const HOP_HEIGHT = 0.3
const HOP_DURATION = 0.4       // seconds for one hop arc
const GREETING_DURATION = 1500 // ms for wave gesture when clicked
const DROP_HEIGHT = 5          // robot starts at this Y (spaceship hover height)
const DROP_DURATION = 0.8      // seconds to fall from ship to ground
const BOUNCE_HEIGHT = 0.4      // small bounce on landing
const BOUNCE_DURATION = 0.3

// Animation state graph — parameter-driven transitions
const STATE_GRAPH = {
  layers: [{
    name: 'agent',
    states: [
      { name: 'START' },
      { name: 'Idle', speed: 1.0 },
      { name: 'Grab', speed: 1.0 },
      { name: 'Spin', speed: 1.0 },
      { name: 'Miniguns', speed: 1.0 },
      { name: 'Walk', speed: 1.0 },
      { name: 'Jump', speed: 1.0, loop: false },
    ],
    transitions: [
      { from: 'START', to: 'Idle', time: 0, priority: 0 },
      { from: 'Idle', to: 'Walk', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'walking', predicate: pc.ANIM_EQUAL_TO, value: 1 }] },
      { from: 'Walk', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'walking', predicate: pc.ANIM_EQUAL_TO, value: 0 }] },
      // action=1 → Grab, action=2 → Spin, action=3 → Miniguns
      // Direct transitions from ANY action state to any other (no idle gap)
      ...[['Idle', 'Grab', 1], ['Idle', 'Spin', 2], ['Idle', 'Miniguns', 3],
          ['Grab', 'Spin', 2], ['Grab', 'Miniguns', 3], ['Grab', 'Idle', 0],
          ['Spin', 'Grab', 1], ['Spin', 'Miniguns', 3], ['Spin', 'Idle', 0],
          ['Miniguns', 'Grab', 1], ['Miniguns', 'Spin', 2], ['Miniguns', 'Idle', 0],
      ].map(([from, to, val]) => ({
        from: from as string, to: to as string, time: 0.3, priority: 0,
        conditions: [{ parameterName: 'action', predicate: pc.ANIM_EQUAL_TO, value: val as number }],
      })),
      { from: 'Idle', to: 'Jump', time: 0.1, priority: 1,
        conditions: [{ parameterName: 'jumping', predicate: pc.ANIM_EQUAL_TO, value: 1 }] },
      { from: 'Jump', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'jumping', predicate: pc.ANIM_EQUAL_TO, value: 0 }] },
    ],
  }],
  parameters: {
    walking:  { name: 'walking',  type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    action:   { name: 'action',   type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    spinning: { name: 'spinning', type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    jumping:  { name: 'jumping',  type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
  },
}

interface ContainerWithAnims extends pc.ContainerResource { animations: pc.Asset[] }

function findTrack(container: ContainerWithAnims, keyword: string): pc.AnimTrack | null {
  const lower = keyword.toLowerCase()
  for (const a of container.animations) {
    if (a.name.toLowerCase().includes(lower)) return a.resource as pc.AnimTrack
    const track = a.resource as pc.AnimTrack | null
    if (track?.name?.toLowerCase().includes(lower)) return track
  }
  return null
}

type AgentState = 'spawning' | 'working' | 'walking' | 'completing' | 'fading' | 'done'

export class AgentCharacter {
  private wrapper: pc.Entity | null = null
  private appRef: Application | null = null
  private label: AgentLabel | null = null
  private labelEntity: pc.Entity | null = null
  private spaceship: SpaceshipTransport
  private renderEntities: pc.Entity[] = []

  // State machine
  private state: AgentState = 'spawning'
  private stateTimer = 0
  private phraseTimer = 0
  private workDuration = WORK_DURATION_MIN

  // Walking + hop
  private targetX = 0
  private targetZ = 0
  private hopTimer = 0
  private hopNextAt = HOP_INTERVAL_MIN
  private hopProgress = -1  // -1 = not hopping

  // Fade
  private fadeTimer = 0
  private fadeDirection: 'in' | 'out' | 'none' = 'none'
  private pendingComplete = false

  // Drop descent from spaceship
  private dropping = false
  private dropTimer = 0
  private bouncing = false
  private bounceTimer = 0

  // Click interaction
  private greetingTimer = 0
  private isGreeting = false

  // BUD info for click tooltip
  budNumber: number | null = null
  budTitle: string | null = null
  currentAction = ''

  readonly key: string
  readonly skillSlug: string

  constructor(key: string, skillSlug: string) {
    this.key = key
    this.skillSlug = skillSlug
    this.spaceship = new SpaceshipTransport()
  }

  async spawn(
    parent: pc.Entity, loader: AssetLoader, app: Application,
    x: number, z: number, action: string,
  ): Promise<void> {
    this.appRef = app
    const asset = await loader.load(AGENT_ROBOT)
    const container = asset.resource as ContainerWithAnims

    this.wrapper = new pc.Entity(`Agent_${this.skillSlug}_${this.key.slice(0, 6)}`)
    this.wrapper.setPosition(x, 0, z)

    const renderEntity = container.instantiateRenderEntity()
    renderEntity.setLocalScale(ROBOT_SCALE, ROBOT_SCALE, ROBOT_SCALE)
    this.wrapper.addChild(renderEntity)
    this.collectRenderEntities(renderEntity)

    // Use fixed label height — AABB measurement is unreliable for complex robot meshes
    const scaledHeight = LABEL_Y_OVERRIDE

    // Animation setup
    this.wrapper.addComponent('anim', { activate: true })
    this.wrapper.anim!.loadStateGraph(STATE_GRAPH)
    const layer = this.wrapper.anim!.baseLayer
    if (layer) {
      const idle = findTrack(container, 'iddle') ?? findTrack(container, 'idle')
      const grab = findTrack(container, 'grab')
      const spin = findTrack(container, 'attackspin') ?? findTrack(container, 'spin')
      const miniguns = findTrack(container, 'attackminiguns') ?? findTrack(container, 'miniguns')
      const walk = findTrack(container, 'walking') ?? findTrack(container, 'walk')
      const jump = findTrack(container, 'jump')
      if (idle) layer.assignAnimation('Idle', idle)
      if (grab) layer.assignAnimation('Grab', grab)
      if (spin) layer.assignAnimation('Spin', spin)
      if (miniguns) layer.assignAnimation('Miniguns', miniguns)
      if (walk) layer.assignAnimation('Walk', walk)
      if (jump) layer.assignAnimation('Jump', jump)
    }

    // Label — positioned above head, hidden during drop (shown after landing)
    this.label = new AgentLabel(app.app.graphicsDevice)
    this.labelEntity = this.label.create(getSkillDisplayName(this.skillSlug), action)
    this.label.setHeight(scaledHeight + 0.3)
    this.labelEntity.enabled = false  // hidden until robot lands
    this.wrapper.addChild(this.labelEntity)
    app.registerBillboard(this.labelEntity)

    // Make clickable
    this.wrapper.tags.add('pickable')
    setTreeData(this.wrapper, {
      type: 'tree_agent',
      agentKey: this.key,
      skillSlug: this.skillSlug,
      skillName: getSkillDisplayName(this.skillSlug),
    })

    parent.addChild(this.wrapper)
    this.currentAction = action

    // Start spawn: spaceship flies in, robot hidden until drop
    this.state = 'spawning'
    this.stateTimer = 0
    this.setOpacity(0)

    // Init and fly spaceship in — robot drops from ship height when it arrives
    await this.spaceship.init(parent, loader)
    this.spaceship.flyIn(x, z, () => {
      // Ship hovering — make robot visible at ship height, then drop
      this.setOpacity(1)
      this.wrapper?.setPosition(x, DROP_HEIGHT, z)
      this.wrapper?.anim?.setInteger('jumping', 1) // jump/fall animation
      this.dropping = true
      this.dropTimer = 0
    })
  }

  /** Set the next walk target position. */
  setWalkTarget(x: number, z: number): void {
    this.targetX = x
    this.targetZ = z
  }

  /** Start the completion sequence (celebrate + beam out). */
  complete(): void {
    if (this.state === 'spawning') { this.pendingComplete = true; return }
    if (this.state === 'completing' || this.state === 'fading' || this.state === 'done') return
    this.state = 'completing'
    this.stateTimer = 0
    this.label?.setColor(0.3, 1.0, 0.4)
    this.label?.setText(getSkillDisplayName(this.skillSlug), 'Task Complete!')
    this.wrapper?.anim?.setInteger('action', 0)
    this.wrapper?.anim?.setInteger('walking', 0)
    this.wrapper?.anim?.setInteger('jumping', 1)
  }

  updateAction(text: string): void {
    this.currentAction = text
    this.label?.setText(getSkillDisplayName(this.skillSlug), text)
  }

  /** Called when user clicks the robot — play greeting + return info. */
  onClicked(): void {
    if (this.isGreeting || this.state === 'fading' || this.state === 'done') return
    this.isGreeting = true
    this.greetingTimer = 0
    // Use grab animation as a wave gesture
    this.wrapper?.anim?.setInteger('action', 1)
  }

  get isDone(): boolean { return this.state === 'done' }
  getWrapper(): pc.Entity | null { return this.wrapper }

  /** Trigger transition to walking state toward a new tree. */
  startWalking(x: number, z: number): void {
    if (this.state !== 'working') return
    this.targetX = x
    this.targetZ = z
    this.state = 'walking'
    this.wrapper?.anim?.setInteger('action', 0)
    this.wrapper?.anim?.setInteger('walking', 1)
  }

  /** Check if the working timer has expired (ready to walk). */
  get readyToWalk(): boolean { return this.state === 'working' && this.stateTimer >= this.workDuration }

  update(dt: number): void {
    if (!this.wrapper) return

    this.spaceship.update(dt)
    this.updateFade(dt)
    this.updateGreeting(dt)
    this.updateHop(dt)
    this.updateDrop(dt)

    switch (this.state) {
      case 'spawning':
        // Wait for drop + bounce to complete before entering working state
        if (!this.dropping && !this.bouncing) {
          this.stateTimer += dt * 1000
          if (this.stateTimer >= SPAWN_ANIM_MS) {
            this.wrapper.anim?.setInteger('spinning', 0)
            this.wrapper.anim?.setInteger('jumping', 0)
            if (this.pendingComplete) { this.pendingComplete = false; this.complete() }
            else this.enterWorking()
          }
        }
        break

      case 'working':
        this.stateTimer += dt
        this.phraseTimer += dt
        // Constantly cycle through active animations — no idle/T-pose
        // Each action plays for ~4 seconds before switching
        // 1=grab, 2=spin, 3=miniguns — always doing something
        {
          const ACTIONS = [1, 2, 3, 1, 3, 2]
          const cycleIndex = Math.floor(this.stateTimer / 4) % ACTIONS.length
          this.wrapper.anim?.setInteger('action', ACTIONS[cycleIndex])
        }
        // Cycle label phrases
        if (this.phraseTimer >= PHRASE_INTERVAL) {
          this.phraseTimer = 0
          this.label?.setText(getSkillDisplayName(this.skillSlug), getNextPhrase(this.skillSlug))
        }
        break

      case 'walking':
        this.tickWalking(dt)
        break

      case 'completing':
        this.stateTimer += dt * 1000
        if (this.stateTimer >= COMPLETE_PAUSE_MS) {
          // Spaceship comes back for pickup — hold hover while robot beams up
          this.state = 'fading'
          this.wrapper.anim?.setInteger('jumping', 0)
          const pos = this.wrapper.getPosition()
          this.spaceship.reset()
          this.spaceship.flyIn(pos.x, pos.z, () => {
            // Ship hovering — beam up the robot
            this.fadeDirection = 'out'
            this.fadeTimer = 0
          }, true)
        }
        break

      case 'fading':
        // Wait for fade out to complete, then spaceship flies away
        if (this.fadeTimer >= TELEPORT_MS && this.fadeDirection === 'none') {
          if (this.spaceship.isActive) break // wait for ship to finish
          this.state = 'done'
        }
        break
    }
  }

  destroy(): void {
    if (this.labelEntity && this.appRef) this.appRef.unregisterBillboard(this.labelEntity)
    this.label?.destroy()
    this.label = null
    this.labelEntity = null
    this.spaceship.destroy()
    this.wrapper?.destroy()
    this.wrapper = null
    this.appRef = null
    this.renderEntities = []
  }

  // ─── Private helpers ────────────────────────

  private enterWorking(): void {
    this.state = 'working'
    this.stateTimer = 0
    this.phraseTimer = 0
    this.workDuration = WORK_DURATION_MIN + Math.random() * (WORK_DURATION_MAX - WORK_DURATION_MIN)
    this.label?.setText(getSkillDisplayName(this.skillSlug), getNextPhrase(this.skillSlug))
  }

  private tickWalking(dt: number): void {
    if (!this.wrapper) return
    const pos = this.wrapper.getPosition()
    const dx = this.targetX - pos.x
    const dz = this.targetZ - pos.z
    const distSq = dx * dx + dz * dz

    if (distSq < ARRIVE_DIST_SQ) {
      // Arrived at target
      this.wrapper.anim?.setInteger('walking', 0)
      this.enterWorking()
      return
    }

    // Move toward target
    const dist = Math.sqrt(distSq)
    const step = WALK_SPEED * dt
    const nx = dx / dist
    const nz = dz / dist
    this.wrapper.setPosition(pos.x + nx * step, 0, pos.z + nz * step)

    // Face walking direction
    const yaw = Math.atan2(nx, nz) * pc.math.RAD_TO_DEG
    this.wrapper.setEulerAngles(0, yaw, 0)
  }

  private updateFade(dt: number): void {
    if (this.fadeDirection === 'none') return
    this.fadeTimer += dt * 1000
    if (this.fadeDirection === 'in') {
      const t = Math.min(this.fadeTimer / TELEPORT_MS, 1)
      this.setOpacity(t)
      if (t >= 1) this.fadeDirection = 'none'
    } else {
      const t = Math.min(this.fadeTimer / TELEPORT_MS, 1)
      this.setOpacity(1 - t)
      if (t >= 1) {
        this.fadeDirection = 'none'
        // Hide label so it doesn't linger after robot fades out
        if (this.labelEntity) this.labelEntity.enabled = false
        // Robot beamed up — now ship can fly away
        this.spaceship.flyOut(() => {})
      }
    }
  }

  /** Set opacity on all meshes. Only calls mat.update() when blend mode changes. */
  private setOpacity(opacity: number): void {
    const needsBlend = opacity < 1
    for (const entity of this.renderEntities) {
      if (!entity.render) continue
      for (const mi of entity.render.meshInstances) {
        const mat = mi.material as pc.StandardMaterial
        const wasBlending = mat.blendType === pc.BLEND_NORMAL
        mat.opacity = opacity
        // Only update shader variant when blend mode actually changes
        if (needsBlend !== wasBlending) {
          mat.blendType = needsBlend ? pc.BLEND_NORMAL : pc.BLEND_NONE
          mat.depthWrite = !needsBlend
          mat.update()
        }
      }
    }
  }


  private collectRenderEntities(root: pc.Entity): void {
    if (root.render) this.renderEntities.push(root)
    for (const child of root.children as pc.Entity[]) this.collectRenderEntities(child)
  }

  /** Greeting wave when clicked — plays for GREETING_DURATION then resumes. */
  private updateGreeting(dt: number): void {
    if (!this.isGreeting) return
    this.greetingTimer += dt * 1000
    if (this.greetingTimer >= GREETING_DURATION) {
      this.isGreeting = false
      this.greetingTimer = 0
      // Resume idle — action cycle will pick up next animation
      this.wrapper?.anim?.setInteger('action', 0)
    }
  }

  /** Robot drops from spaceship height to ground with bounce on landing. */
  private updateDrop(dt: number): void {
    if (!this.wrapper) return

    if (this.dropping) {
      this.dropTimer += dt
      const t = Math.min(this.dropTimer / DROP_DURATION, 1)
      // Ease-in (accelerating fall like gravity)
      const eased = t * t
      const y = DROP_HEIGHT * (1 - eased)
      const pos = this.wrapper.getPosition()
      this.wrapper.setPosition(pos.x, y, pos.z)

      if (t >= 1) {
        this.dropping = false
        this.bouncing = true
        this.bounceTimer = 0
        this.wrapper.setPosition(pos.x, 0, pos.z)
      }
    } else if (this.bouncing) {
      this.bounceTimer += dt
      const t = Math.min(this.bounceTimer / BOUNCE_DURATION, 1)
      // Sine arc for bounce — up then back to ground
      const bounceY = Math.sin(t * Math.PI) * BOUNCE_HEIGHT
      const pos = this.wrapper.getPosition()
      this.wrapper.setPosition(pos.x, bounceY, pos.z)

      if (t >= 1) {
        this.bouncing = false
        this.stateTimer = 0 // start spawn timer after landing
        const p = this.wrapper.getPosition()
        this.wrapper.setPosition(p.x, 0, p.z)
        // Show label after landing
        if (this.labelEntity) this.labelEntity.enabled = true
      }
    }
  }

  /** Random hops while walking — playful bouncing robot. */
  private updateHop(dt: number): void {
    if (this.state !== 'walking' || !this.wrapper) return

    this.hopTimer += dt
    if (this.hopProgress < 0) {
      // Not currently hopping — check if it's time for one
      if (this.hopTimer >= this.hopNextAt) {
        this.hopProgress = 0
        this.hopTimer = 0
        this.hopNextAt = HOP_INTERVAL_MIN + Math.random() * (HOP_INTERVAL_MAX - HOP_INTERVAL_MIN)
      }
    } else {
      // Currently hopping — sine arc
      this.hopProgress += dt / HOP_DURATION
      if (this.hopProgress >= 1) {
        this.hopProgress = -1
        // Ensure Y returns to ground
        const pos = this.wrapper.getPosition()
        this.wrapper.setPosition(pos.x, 0, pos.z)
      } else {
        const hopY = Math.sin(this.hopProgress * Math.PI) * HOP_HEIGHT
        const pos = this.wrapper.getPosition()
        this.wrapper.setPosition(pos.x, hopY, pos.z)
      }
    }
  }
}
