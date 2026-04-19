// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
    colorWarp: 15,              // drives trunk-to-tip brightening via wiggleColor bias
    minSize: 5 * WORLD_SCALE,
  }
}

export function defaultBranch(): TreeRules {
  return {
    growLean: 0.3,             // phototropism — pulls branches toward vertical, prevents extreme droop
    angle: Math.PI / 3.5,      // ~51°
    angleWarp: Math.PI / 6,    // 30°
    size: 0.7,
    sizeWarp: 0.3,
    whorl: 0,
    whorlWarp: 0,
    colorWarp: 12,              // tips approach white after ~10 generations
    minSize: 10 * WORLD_SCALE,
  }
}

function wiggle(value: number, warp: number): number {
  return value + (Math.random() - 0.5) * warp
}

/**
 * Shift color toward white each generation — port of Java's trunk-to-tip brightening.
 * Original: rgb[i] += level (bias) then ± random shake. Net drift: +level/gen.
 * Tips naturally approach white after ~10 generations, creating the glow gradient.
 */
export function wiggleColor(color: Color3, level: number): Color3 {
  return color.map(c =>
    Math.max(0, Math.min(255, c + Math.round(level + (Math.random() - 0.5) * level * 2)))
  ) as Color3
}

/** Build rotation matrix for next branch segment. */
export function getRulesMatrix(rules: TreeRules): Mat3 {
  const yRot = Mat3.rotateY(wiggle(rules.whorl, rules.whorlWarp))
  const xRot = Mat3.rotateX(wiggle(rules.angle, rules.angleWarp))
  return Mat3.identity().multiply(yRot).multiply(xRot)
}

