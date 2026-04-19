// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CoffeeBarScene — builds the coffee bar interior geometry.
 *
 * Follows the house-interior pattern (`housetest/InteriorScene.ts`):
 *   - `buildRoom` builds the shell (floor + walls).
 *   - `buildFurniture` iterates `COFFEE_BAR_LAYOUT` and places every item in
 *     a single uniform loop.
 *   - `buildMenuBoard` adds the one hand-composed prop (chalkboard menu).
 *
 * All per-item positions / rotations / sizes / stacking live in
 * CoffeeBarLayout.ts — this class is just the runner.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { ChalkboardRenderer } from '../rendering/ChalkboardRenderer'
import { COFFEE_ROOM, COFFEE_COLLISION } from './SceneConfig'
import type { CollisionBox } from '../housetest/CollisionSystem'
import { placeScaledFurniture } from './ScaledFurniture'
import { COFFEE_BAR_LAYOUT, COUNTER } from './CoffeeBarLayout'

export class CoffeeBarScene {
  private factory: BuildingFactory

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(root: pc.Entity, app: Application): Promise<CollisionBox[]> {
    await this.buildRoom(root)
    this.buildCounter(root)
    await this.buildFurniture(root, app)
    this.buildMenuBoard(root, app)
    return COFFEE_COLLISION
  }

  // ─── Room shell ─────────────────────────────────────────────────────────

  private async buildRoom(root: pc.Entity): Promise<void> {
    await this.factory.createFloor(root, COFFEE_ROOM.width, COFFEE_ROOM.depth)
    await this.factory.createWalls(root, COFFEE_ROOM.width, COFFEE_ROOM.depth, [
      { side: 'front', index: COFFEE_ROOM.doorIndex, type: 'door' },
      { side: 'left',  index: 1, type: 'window' },
      { side: 'left',  index: 2, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
      { side: 'right', index: 2, type: 'window' },
    ])
  }

  // ─── Counter — two-tier wooden structure along the back wall ───────────

  private buildCounter(root: pc.Entity): void {
    const materials = this.factory.materialFactory
    if (!materials) return

    const counterMat = materials.getColor('counter_wood', 0.45, 0.30, 0.18, {
      metalness: 0.0, gloss: 0.25,
    })
    const trimMat = materials.getColor('counter_trim', 0.32, 0.21, 0.12, {
      metalness: 0.0, gloss: 0.3,
    })

    const addBox = (
      name: string,
      sx: number, sy: number, sz: number,
      px: number, py: number, pz: number,
      mat: pc.Material,
    ): void => {
      const e = new pc.Entity(name)
      e.addComponent('render', { type: 'box' })
      e.setLocalScale(sx, sy, sz)
      e.setLocalPosition(px, py, pz)
      if (e.render) {
        for (const mi of e.render.meshInstances) mi.material = mat
      }
      root.addChild(e)
    }

    // Main counter body (customer-facing tier)
    addBox('Counter',
      COUNTER.width, COUNTER.topY, COUNTER.depth,
      COUNTER.centreX, COUNTER.topY / 2, COUNTER.centreZ,
      counterMat,
    )

    // Raised back step (barista-side equipment shelf). Sits flush against
    // the back edge of the main counter, runs full width.
    const stepHeight = COUNTER.backStepY - COUNTER.topY
    const backZ = COUNTER.centreZ - COUNTER.depth / 2 + COUNTER.backStepDepth / 2
    addBox('CounterBackStep',
      COUNTER.width, stepHeight, COUNTER.backStepDepth,
      COUNTER.centreX, COUNTER.topY + stepHeight / 2, backZ,
      counterMat,
    )

    // Darker trim along the customer-facing top edge — makes it read as
    // proper carpentry rather than a plain box.
    const trimHeight = 0.04
    addBox('CounterTrim',
      COUNTER.width, trimHeight, 0.02,
      COUNTER.centreX, COUNTER.topY - trimHeight / 2,
      COUNTER.centreZ + COUNTER.depth / 2 + 0.01,
      trimMat,
    )
  }

  // ─── Furniture — data-driven loop ───────────────────────────────────────

  private async buildFurniture(root: pc.Entity, app: Application): Promise<void> {
    // Map from asset path → top-surface world Y of the most recently placed
    // entity with that asset. Used by `stackOn` so a mug can sit on a table
    // without the layout knowing the table's height.
    const topOf = new Map<string, number>()

    for (const item of COFFEE_BAR_LAYOUT) {
      const y = item.stackOn !== undefined
        ? topOf.get(item.stackOn) ?? 0
        : item.y ?? 0

      const { size } = await placeScaledFurniture(
        this.factory.assetLoader, app, root, item.asset, item.x, y, item.z,
        { maxDim: item.fit, yaw: item.rotation },
      )

      topOf.set(item.asset, y + size.y)
    }
  }

  // ─── Chalkboard menu — one hand-composed wall prop ──────────────────────

  private buildMenuBoard(root: pc.Entity, app: Application): void {
    const materials = this.factory.materialFactory
    if (!materials) return

    // Mounted on the empty left stretch of the back wall — coffee machine
    // (x=2.5) and cash register (x=3.8) cluster on the right, so the menu
    // sits at x=MENU_CENTRE_X where nothing on the counter blocks it.
    const boardWidth = 1.1
    const boardHeight = 0.4
    const frameThick = 0.04
    const frameDepth = 0.03
    const menuCentreY = COUNTER.topY + boardHeight / 2 + 0.1
    const MENU_CENTRE_X = 1.2

    const group = new pc.Entity('MenuBoard')
    // Pushed slightly forward so the frame doesn't z-fight the back wall.
    group.setLocalPosition(MENU_CENTRE_X, menuCentreY, 0.09)
    root.addChild(group)

    const frameMat = materials.getColor('menu_frame', 0.54, 0.37, 0.24, {
      metalness: 0.0, gloss: 0.25,
    })

    const addRail = (
      name: string,
      sx: number, sy: number, sz: number,
      px: number, py: number, pz: number,
    ): void => {
      const rail = new pc.Entity(name)
      rail.addComponent('render', { type: 'box' })
      rail.setLocalScale(sx, sy, sz)
      rail.setLocalPosition(px, py, pz)
      if (rail.render) {
        for (const mi of rail.render.meshInstances) mi.material = frameMat
      }
      group.addChild(rail)
    }

    const outerW = boardWidth + frameThick * 2
    addRail('RailTop',    outerW,     frameThick,  frameDepth, 0,  boardHeight / 2 + frameThick / 2, 0)
    addRail('RailBottom', outerW,     frameThick,  frameDepth, 0, -boardHeight / 2 - frameThick / 2, 0)
    addRail('RailLeft',   frameThick, boardHeight, frameDepth, -boardWidth / 2 - frameThick / 2, 0, 0)
    addRail('RailRight',  frameThick, boardHeight, frameDepth,  boardWidth / 2 + frameThick / 2, 0, 0)

    // ChalkboardRenderer returns a plane with its normal on +Y; rotate +90°
    // around X so the normal tilts to +Z (toward the viewer inside the room).
    const board = ChalkboardRenderer.create(app, {
      title: '\u2615 MENU',
      items: ['ESPRESSO', 'LATTE', 'CAPPUCCINO', 'TEA'],
      width: boardWidth,
      height: boardHeight,
    })
    board.setLocalEulerAngles(90, 0, 0)
    board.setLocalPosition(0, 0, frameDepth / 2 + 0.002)
    group.addChild(board)
  }
}
