/**
 * TreeRules — branch generation parameters.
 * Direct port of Tree3D's TreeData3D.java.
 */
import { Mat3 } from './Mat3'

export type Color3 = [number, number, number] // RGB 0–255

export interface TreeRules {
  minSize: number       // stop growing below this size
  angle: number         // axil angle (radians)
  angleWarp: number     // random spread on axil
  size: number          // child/parent size ratio
  sizeWarp: number      // random spread on size
  whorl: number         // radial rotation around stem (radians)
  whorlWarp: number     // random spread on whorl
  growLean: number      // phototropism: 1=toward goal, -1=away
  colorWarp: number     // color variation per generation
}

/** Java pixel units → PlayCanvas world units. Shared with Tree3DSystem. */
export const WORLD_SCALE = 0.015

export function defaultTrunk(): TreeRules {
  return {
    growLean: 0,
    angle: 0,
    angleWarp: Math.PI / 9,    // 20°
    size: 0.8,
    sizeWarp: 0.2,
    whorl: Math.PI * 2 / 3,    // 120°
    whorlWarp: 0,
    colorWarp: 30,
    minSize: 5 * WORLD_SCALE,
  }
}

export function defaultBranch(): TreeRules {
  return {
    growLean: 0,
    angle: Math.PI / 3.5,      // ~51°
    angleWarp: Math.PI / 6,    // 30°
    size: 0.7,
    sizeWarp: 0.3,
    whorl: 0,
    whorlWarp: 0,
    colorWarp: 3,
    minSize: 10 * WORLD_SCALE,
  }
}

function wiggle(value: number, warp: number): number {
  return value + (Math.random() - 0.5) * warp
}

export function wiggleColor(color: Color3, level: number): Color3 {
  const shake = level * 2 + 1
  const rgb: Color3 = [
    color[0] + level, // bias toward yellow
    color[1] + level, // bias toward green
    color[2],
  ]
  for (let i = 0; i < 3; i++) {
    rgb[i] = Math.max(0, Math.min(255, rgb[i] + Math.floor(Math.random() * shake) - level))
  }
  return rgb
}

/** Build rotation matrix for next branch segment. */
export function getRulesMatrix(rules: TreeRules): Mat3 {
  const yRot = Mat3.rotateY(wiggle(rules.whorl, rules.whorlWarp))
  const xRot = Mat3.rotateX(wiggle(rules.angle, rules.angleWarp))
  return Mat3.identity().multiply(yRot).multiply(xRot)
}

export function blendRules(d1: TreeRules, d2: TreeRules, ratio: number): TreeRules {
  const lerp = (a: number, b: number) => a * (1 - ratio) + b * ratio
  return {
    growLean: lerp(d1.growLean, d2.growLean),
    angle: lerp(d1.angle, d2.angle),
    angleWarp: lerp(d1.angleWarp, d2.angleWarp),
    size: lerp(d1.size, d2.size),
    sizeWarp: lerp(d1.sizeWarp, d2.sizeWarp),
    whorl: lerp(d1.whorl, d2.whorl),
    whorlWarp: lerp(d1.whorlWarp, d2.whorlWarp),
    colorWarp: Math.round(lerp(d1.colorWarp, d2.colorWarp)),
    minSize: d2.minSize,
  }
}
