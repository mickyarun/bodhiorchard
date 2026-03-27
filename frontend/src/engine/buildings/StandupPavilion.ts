/**
 * StandupPavilion — Standup meeting hut with whiteboards.
 *
 * Layout (top-down, Z increases toward front):
 *
 *   z=0 [====== BACK WALL (solid, whiteboards) ======]
 *       | [Whiteboard 1]    [Whiteboard 2]          |
 *   z=1 |              Standup Table                 |
 *       |   Stand  Stand  Stand  Stand               |
 *   z=2 [============ FRONT (open) ==================]
 *       x=0                                      x=3
 *
 * The hut is a 3×2 enclosed shelter with open front, whiteboards
 * on the back wall, a central standup table, and standing spots.
 * String lights frame the entrance.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from './BuildingFactory'
import { BUILDING } from '../assets/AssetManifest'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { ExclusionZone } from '../utils/MathUtils'

export interface PavilionResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
}

const WALL_HEIGHT = 1.29
const HUT_WIDTH = 3
const HUT_DEPTH = 2

// Whiteboard dimensions (world units)
const WB_WIDTH = 1.0
const WB_HEIGHT = 0.65
const WB_Y = 0.8            // center height — fits within WALL_HEIGHT (top at 1.125)
const WB_Z = 0.08           // slight offset from back wall

// Sticky note colors (pastel) — 3-4 per whiteboard
const STICKY_COLORS: Array<[number, number, number]> = [
  [1.0, 0.92, 0.4],   // yellow
  [0.55, 0.85, 1.0],  // blue
  [1.0, 0.6, 0.65],   // pink
  [0.6, 1.0, 0.65],   // green
  [1.0, 0.75, 0.45],  // orange
]

export class StandupPavilion {
  private factory: BuildingFactory
  private materials: pc.StandardMaterial[] = []  // tracked for cleanup

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  /** Destroy all GPU materials created by this builder. Call during teardown. */
  destroy(): void {
    for (const mat of this.materials) mat.destroy()
    this.materials = []
  }

  async build(app: Application, x: number, z: number): Promise<PavilionResult> {
    const root = new pc.Entity('StandupPavilion')
    root.setPosition(x, 0, z)

    const seats: InteractionPoint[] = []

    // ─── Shelter hut (3×2 tiles, open front) ───
    await this.factory.createFloor(root, HUT_WIDTH, HUT_DEPTH)
    await this.factory.createWalls(root, HUT_WIDTH, HUT_DEPTH, [
      { side: 'front', index: 0, type: 'door' },
      { side: 'front', index: 1, type: 'door' },
      { side: 'front', index: 2, type: 'door' },
      { side: 'left', index: 0, type: 'window' },
      { side: 'right', index: 0, type: 'window' },
    ])
    this.factory.createRoof(root, HUT_WIDTH, HUT_DEPTH, WALL_HEIGHT)

    // ─── Peaked hut roof (gabled A-frame above flat roof) ───
    this.createGabledRoof(root, HUT_WIDTH, HUT_DEPTH, WALL_HEIGHT)

    // ─── Whiteboards on back wall ───
    this.createWhiteboard(root, 0.75, WB_Y, WB_Z)
    this.createWhiteboard(root, 2.25, WB_Y, WB_Z)

    // ─── Central standup table ───
    await this.factory.placeFurnitureCentered(root, BUILDING.table, 1.5, 0, 1.2)

    // ─── Standing spots around the table ───
    let seatIndex = 0
    const standPositions: Array<{ lx: number; lz: number; yaw: number }> = [
      { lx: 0.5, lz: 1.2, yaw: 90 },    // left of table
      { lx: 2.5, lz: 1.2, yaw: -90 },   // right of table
      { lx: 1.5, lz: 1.8, yaw: 0 },     // front of table
      { lx: 1.5, lz: 0.6, yaw: 180 },   // back of table (facing boards)
    ]

    for (const sp of standPositions) {
      const seat = BuildingFactory.createInteractionSeat(
        'pavilion', seatIndex++,
        x + sp.lx, z + sp.lz,
        sp.yaw, 'standingSpot', 'idle',
      )
      seats.push(seat)
    }

    // ─── Corner decoration ───
    await this.factory.placeFurnitureCentered(root, BUILDING.plantSmall1, 0.3, 0, 0.3)
    await this.factory.placeFurnitureCentered(root, BUILDING.books, 2.7, 0, 0.3)

    // ─── String lights across entrance ───
    const stringH = WALL_HEIGHT + 1.2
    this.factory.createStringLights(root, [
      // Across front opening
      { start: { x: -0.3, y: stringH, z: HUT_DEPTH }, end: { x: HUT_WIDTH + 0.3, y: stringH, z: HUT_DEPTH }, bulbCount: 4 },
      // Left side down
      { start: { x: -0.3, y: stringH, z: 0 }, end: { x: -0.3, y: stringH, z: HUT_DEPTH }, bulbCount: 2 },
      // Right side down
      { start: { x: HUT_WIDTH + 0.3, y: stringH, z: 0 }, end: { x: HUT_WIDTH + 0.3, y: stringH, z: HUT_DEPTH }, bulbCount: 2 },
    ])

    app.root.addChild(root)

    return {
      entity: root,
      exclusionZone: { x, z, radius: 6 },
      seats,
    }
  }

  // ─── Gabled roof (A-frame peaked roof) ─────────────────────────────────────

  /**
   * Creates a peaked gabled roof above the flat roof.
   * Two angled planes form the A-shape, plus triangular end caps.
   * Gives the hut a charming cottage/hut silhouette.
   */
  private createGabledRoof(
    parent: pc.Entity,
    width: number,
    depth: number,
    baseHeight: number,
  ): void {
    const peakHeight = 0.7    // how high the ridge rises above the flat roof
    const overhang = 0.25     // roof extends beyond walls on each side
    const roofThickness = 0.05

    const centerX = width / 2
    const centerZ = depth / 2
    const ridgeY = baseHeight + peakHeight

    // Roof material — warm brown/terracotta
    const roofMat = new pc.StandardMaterial()
    this.materials.push(roofMat)
    roofMat.diffuse = new pc.Color(0.55, 0.35, 0.2)
    roofMat.metalness = 0
    roofMat.gloss = 0.15
    roofMat.cull = pc.CULLFACE_NONE
    roofMat.update()

    // Calculate slope angle: atan(peakHeight / halfWidth)
    const halfSpan = (width / 2) + overhang
    const slopeAngle = Math.atan2(peakHeight, halfSpan) * (180 / Math.PI)
    // Slope length (hypotenuse)
    const slopeLen = Math.sqrt(peakHeight * peakHeight + halfSpan * halfSpan)

    // Left slope (rotated around Z axis)
    const leftSlope = new pc.Entity('RoofLeft')
    leftSlope.addComponent('render', { type: 'box' })
    leftSlope.setLocalScale(slopeLen, roofThickness, depth + overhang * 2)
    leftSlope.setLocalPosition(
      centerX - halfSpan / 2,
      baseHeight + peakHeight / 2,
      centerZ,
    )
    leftSlope.setLocalEulerAngles(0, 0, slopeAngle)
    leftSlope.render!.meshInstances[0].material = roofMat
    leftSlope.render!.castShadows = true
    parent.addChild(leftSlope)

    // Right slope (mirror)
    const rightSlope = new pc.Entity('RoofRight')
    rightSlope.addComponent('render', { type: 'box' })
    rightSlope.setLocalScale(slopeLen, roofThickness, depth + overhang * 2)
    rightSlope.setLocalPosition(
      centerX + halfSpan / 2,
      baseHeight + peakHeight / 2,
      centerZ,
    )
    rightSlope.setLocalEulerAngles(0, 0, -slopeAngle)
    rightSlope.render!.meshInstances[0].material = roofMat
    rightSlope.render!.castShadows = true
    parent.addChild(rightSlope)

    // Ridge beam along the peak
    const ridge = new pc.Entity('Ridge')
    ridge.addComponent('render', { type: 'box' })
    ridge.setLocalScale(0.06, 0.06, depth + overhang * 2)
    ridge.setLocalPosition(centerX, ridgeY, centerZ)
    ridge.render!.meshInstances[0].material = roofMat
    ridge.render!.castShadows = false
    parent.addChild(ridge)

  }

  // ─── Whiteboard creation (procedural geometry) ────────────────────────────

  /**
   * Creates a whiteboard with sticky notes on the back wall.
   * Board is a white plane + thin dark frame, with colored sticky note planes.
   */
  private createWhiteboard(parent: pc.Entity, cx: number, cy: number, cz: number): void {
    const board = new pc.Entity('Whiteboard')
    board.setLocalPosition(cx, cy, cz)
    // Rotate so plane faces +Z (toward room interior)
    board.setLocalEulerAngles(90, 0, 0)

    // White board surface
    board.addComponent('render', { type: 'plane' })
    board.setLocalScale(WB_WIDTH, 1, WB_HEIGHT)

    const boardMat = new pc.StandardMaterial(); this.materials.push(boardMat)
    boardMat.diffuse = new pc.Color(0.95, 0.95, 0.97)
    boardMat.metalness = 0
    boardMat.gloss = 0.35
    boardMat.update()
    board.render!.meshInstances[0].material = boardMat
    board.render!.castShadows = false

    parent.addChild(board)

    // Frame (4 thin dark bars around the board edges)
    const frameMat = new pc.StandardMaterial(); this.materials.push(frameMat)
    frameMat.diffuse = new pc.Color(0.25, 0.25, 0.28)
    frameMat.metalness = 0.1
    frameMat.gloss = 0.2
    frameMat.update()

    const frameW = 0.03  // frame bar thickness
    const halfW = WB_WIDTH / 2
    const halfH = WB_HEIGHT / 2

    const frameBars: Array<{ lx: number; ly: number; sx: number; sy: number }> = [
      { lx: 0, ly: halfH, sx: WB_WIDTH + frameW, sy: frameW },     // top
      { lx: 0, ly: -halfH, sx: WB_WIDTH + frameW, sy: frameW },    // bottom
      { lx: -halfW, ly: 0, sx: frameW, sy: WB_HEIGHT },             // left
      { lx: halfW, ly: 0, sx: frameW, sy: WB_HEIGHT },              // right
    ]

    for (const bar of frameBars) {
      const frameBar = new pc.Entity('Frame')
      frameBar.addComponent('render', { type: 'plane' })
      frameBar.setLocalPosition(cx + bar.lx, cy + bar.ly, cz - 0.005)
      frameBar.setLocalEulerAngles(90, 0, 0)
      frameBar.setLocalScale(bar.sx, 1, bar.sy)
      frameBar.render!.meshInstances[0].material = frameMat
      frameBar.render!.castShadows = false
      parent.addChild(frameBar)
    }

    // Sticky notes (3-4 small colored rectangles scattered on the board)
    const noteCount = 3 + Math.floor(Math.random() * 2)
    for (let i = 0; i < noteCount; i++) {
      const note = new pc.Entity('StickyNote')
      const nx = cx + (Math.random() - 0.5) * (WB_WIDTH * 0.7)
      const ny = cy + (Math.random() - 0.5) * (WB_HEIGHT * 0.5)
      note.setLocalPosition(nx, ny, cz - 0.01)
      note.setLocalEulerAngles(90, (Math.random() - 0.5) * 12, 0) // slight random tilt
      const noteSize = 0.1 + Math.random() * 0.08
      note.setLocalScale(noteSize, 1, noteSize * 0.75)

      note.addComponent('render', { type: 'plane' })
      const color = STICKY_COLORS[i % STICKY_COLORS.length]
      const noteMat = new pc.StandardMaterial(); this.materials.push(noteMat)
      noteMat.diffuse = new pc.Color(color[0], color[1], color[2])
      noteMat.metalness = 0
      noteMat.gloss = 0.1
      noteMat.update()
      note.render!.meshInstances[0].material = noteMat
      note.render!.castShadows = false
      parent.addChild(note)
    }
  }
}
