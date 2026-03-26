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

// ─── Tree Species Presets ────────────────────────

export interface TreePreset {
  name: string
  trunk: TreeRules
  branch: TreeRules
  rootColor: Color3
  sizeMultiplier: number  // relative to default rootSize
}

/** Broad oak — wide canopy, strong branching. */
export function oakPreset(): TreePreset {
  return {
    name: 'Oak',
    trunk: { ...defaultTrunk(), angle: 0, angleWarp: Math.PI / 7, whorl: Math.PI * 2 / 3 },
    branch: { ...defaultBranch(), angle: Math.PI / 3, size: 0.72, growLean: 0.15 },
    rootColor: [140, 110, 80],
    sizeMultiplier: 1.0,
  }
}

/** Tall pine — upright, narrow, smaller branch angle. */
export function pinePreset(): TreePreset {
  return {
    name: 'Pine',
    trunk: { ...defaultTrunk(), angle: 0, angleWarp: Math.PI / 18, size: 0.85 },
    branch: { ...defaultBranch(), angle: Math.PI / 2.2, size: 0.6, angleWarp: Math.PI / 8, growLean: -0.3 },
    rootColor: [100, 130, 90],
    sizeMultiplier: 1.2,
  }
}

/** Willow — droopy branches, strong downward lean. */
export function willowPreset(): TreePreset {
  return {
    name: 'Willow',
    trunk: { ...defaultTrunk(), angle: 0, angleWarp: Math.PI / 6, size: 0.82 },
    branch: { ...defaultBranch(), angle: Math.PI / 4, size: 0.75, growLean: -0.6, minSize: 6 * WORLD_SCALE },
    rootColor: [160, 180, 130],
    sizeMultiplier: 0.9,
  }
}

/** Wild — chaotic, lots of warp. Port of Java's TreeData3D.Random(). */
export function randomPreset(): TreePreset {
  const randGauss = () => {
    // Box-Muller transform for Gaussian
    const u1 = Math.random(), u2 = Math.random()
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
  }
  const randomRules = (minSize: number, colorWarp: number): TreeRules => {
    let size = randGauss() / 12 + 0.75
    while (size > 0.95 || size < 0) size = size * 0.75 + 0.2
    return {
      growLean: Math.random() * 2 - 1,
      angle: Math.abs(randGauss()) * Math.PI / 2,
      angleWarp: Math.abs(randGauss()) * Math.PI / 4,
      size,
      sizeWarp: Math.random() * Math.PI / 2,
      whorl: Math.random() * Math.PI,
      whorlWarp: Math.abs(randGauss()) * Math.PI / 4,
      colorWarp,
      minSize: minSize * WORLD_SCALE,
    }
  }
  const r = Math.random()
  const baseColor: Color3 = [
    80 + Math.floor(r * 120),
    80 + Math.floor(Math.random() * 120),
    60 + Math.floor(Math.random() * 80),
  ]
  return {
    name: 'Wild',
    trunk: randomRules(5, 30),
    branch: randomRules(10, 3),
    rootColor: baseColor,
    sizeMultiplier: 0.7 + Math.random() * 0.6,
  }
}

export const PRESETS = [oakPreset, pinePreset, willowPreset, randomPreset] as const

