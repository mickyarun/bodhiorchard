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

  /** Root constructor: position + size + color, identity rotation. */
  constructor(x: number, y: number, z: number, size: number, color: Color3)
  /** Child constructor: inherits parent tip, new rotation + size. */
  constructor(root: Vec3, size: number, rotation: Mat3, color: Color3)
  constructor(
    xOrRoot: number | Vec3, yOrSize: number,
    zOrRotation?: number | Mat3, sizeOrColor?: number | Color3, color?: Color3,
  ) {
    if (typeof xOrRoot === 'number') {
      // Root constructor
      this.root = new Vec3(xOrRoot, yOrSize, zOrRotation as number)
      this.size = sizeOrColor as number
      this.color = color!
      this.rotation = Mat3.identity()
      // +Y is up in PlayCanvas (Java used -Y)
      this.tip = this.rotation.multiplyVec3(new Vec3(0, this.size, 0))
    } else {
      // Child constructor
      this.root = xOrRoot
      this.size = yOrSize
      this.rotation = zOrRotation as Mat3
      this.color = sizeOrColor as Color3
      this.tip = new Vec3(0, 0, 0) // set by rotateTip after construction
    }
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

  /** Get tip position during growth animation. */
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

    const childSize = this.size * rules.size
    const newRotation = this.rotation.multiply(getRulesMatrix(rules))
    const baby = new TreeBranch(
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
