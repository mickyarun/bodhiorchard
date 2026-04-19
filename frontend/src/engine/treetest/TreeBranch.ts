// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * TreeBranch — recursive branch node.
 * Direct port of Tree3D's TreeBranch3D.java.
 *
 * Y-axis flipped for PlayCanvas: +Y is UP (Java used -Y).
 * No rendering logic — pure data structure.
 */
import { Vec3 } from './Vec3'
import { Mat3 } from './Mat3'
import { type TreeRules, type Color3, getRulesMatrix, wiggleColor } from './TreeRules'

export class TreeBranch {
  root: Vec3          // world-space position of branch base
  tip: Vec3           // local-space tip offset
  rotation: Mat3      // accumulated orientation matrix
  growthSize = 0      // current animated growth (0 → size)
  size: number        // full length of this segment
  color: Color3
  babies: TreeBranch[] = []

  // Static scratch for getGrowTipInto — zero allocation in the hot per-frame update path
  private static readonly _scratchDir = new Vec3(0, 0, 0)

  private constructor(root: Vec3, size: number, rotation: Mat3, color: Color3) {
    this.root     = root
    this.size     = size
    this.rotation = rotation
    this.color    = color
    this.tip      = new Vec3(0, 0, 0)
  }

  /** Create the root branch at a world position with identity rotation. */
  static createRoot(x: number, y: number, z: number, size: number, color: Color3): TreeBranch {
    const b = new TreeBranch(new Vec3(x, y, z), size, Mat3.identity(), color)
    b.tip = b.rotation.multiplyVec3(new Vec3(0, size, 0))
    return b
  }

  /** Create a child branch positioned at a parent tip. */
  static createChild(root: Vec3, size: number, rotation: Mat3, color: Color3): TreeBranch {
    return new TreeBranch(root, size, rotation, color)
  }

  /** Apply phototropism: rotate tip toward goal direction. */
  rotateTip(goal: Vec3, levity: number): Vec3 {
    const tipLocal = new Vec3(0, this.size, 0)

    if (levity > 0) {
      const rtip = this.rotation.multiplyVec3(tipLocal)
      const followLight = Mat3.rotateToward(rtip, goal, levity)
      this.rotation = followLight.multiply(this.rotation)
      return this.rotation.multiplyVec3(tipLocal)
    } else if (levity < 0) {
      const negGoal = goal.negate()
      const rtip = this.rotation.multiplyVec3(tipLocal)
      const followLight = Mat3.rotateToward(rtip, negGoal, -levity)
      this.rotation = followLight.multiply(this.rotation)
      return this.rotation.multiplyVec3(tipLocal)
    } else {
      return this.rotation.multiplyVec3(tipLocal)
    }
  }

  /**
   * Write the animated grow-tip direction into an existing Vec3 — zero allocation.
   * Use in the per-frame update path instead of getGrowTip().
   */
  getGrowTipInto(out: Vec3): void {
    TreeBranch._scratchDir.x = 0
    TreeBranch._scratchDir.y = this.growthSize
    TreeBranch._scratchDir.z = 0
    this.rotation.multiplyVec3Into(TreeBranch._scratchDir, out)
  }

  /** Get tip position during growth animation. Allocates — prefer getGrowTipInto for hot paths. */
  getGrowTip(): Vec3 {
    return this.rotation.multiplyVec3(new Vec3(0, this.growthSize, 0))
  }

  /** World-space tip = root + local tip. */
  getTip(): Vec3 {
    return this.root.add(this.tip)
  }

  /** Create a child branch using the given rules. Returns null if terminal. */
  makeBaby(rules: TreeRules, goal: Vec3): TreeBranch | null {
    if (this.size < rules.minSize) return null

    const childSize   = this.size * rules.size
    const newRotation = this.rotation.multiply(getRulesMatrix(rules))
    const baby = TreeBranch.createChild(
      this.getTip(),
      childSize,
      newRotation,
      wiggleColor(this.color, rules.colorWarp),
    )
    baby.tip = baby.rotateTip(goal, rules.growLean)
    this.babies.push(baby)
    return baby
  }

  /** Animate growth. Returns true when fully grown and ready to spawn children. */
  grow(amount: number): boolean {
    this.growthSize += amount
    if (this.growthSize >= this.size) {
      this.growthSize = this.size
      return true
    }
    return false
  }
}
