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
 * Theme — the single source of truth for every color and grade decision in
 * the garden's visual pass ("spring morning" art direction: vibrant stylized
 * low-poly, warm sun + cool ambient).
 *
 * Conventions:
 *   - `Rgb255` tuples are 0–255 (texture/canvas work, palette data).
 *   - `toColor()` converts to a pc.Color for material/light properties.
 *   - Systems read from here; no system hardcodes its own hex values.
 *
 * Consistency rule that makes the horizon read seamless: FOG.color,
 * SKY.horizon, CAMERA.clearColor, and the IBL horizon must stay in the
 * same family — change one, re-check the other three.
 */
import * as pc from 'playcanvas'

export type Rgb255 = readonly [number, number, number]

/** Convert a 0–255 RGB tuple to a pc.Color (optionally with alpha). */
export function toColor(rgb: Rgb255, a = 1): pc.Color {
  return new pc.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, a)
}

/** CSS rgb() string for Canvas2D texture work. */
export function toCss(rgb: Rgb255, a?: number): string {
  return a === undefined
    ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`
    : `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${a})`
}

export const Theme = {
  SKY: {
    zenith:       [62, 126, 224] as Rgb255,   // saturated spring blue
    mid:          [95, 165, 240] as Rgb255,
    lowerSky:     [150, 198, 248] as Rgb255,
    horizon:      [205, 228, 248] as Rgb255,  // bright warm-blue haze
    nearHorizon:  [222, 232, 240] as Rgb255,  // warm band just above ground
    belowHorizon: [110, 160, 88] as Rgb255,   // spring green ground fade
    belowDeep:    [88, 138, 70] as Rgb255,
    sunHalo:      [255, 238, 190] as Rgb255,
    sunCore:      [255, 252, 240] as Rgb255,
  },

  FOG: {
    color: [205, 226, 244] as Rgb255,  // = SKY.horizon family, slightly warm
    start: 220,
    end:   750,
  },

  CAMERA: {
    clearColor: [205, 228, 248] as Rgb255,  // matches SKY.horizon
    fov: 55,  // retuned in the composition step
  },

  LIGHT: {
    sun:          [255, 230, 189] as Rgb255,  // warm golden
    sunIntensity: 2.1,
    fill:         [140, 173, 235] as Rgb255,  // cool sky bounce
    fillIntensity: 0.75,
    ambient:      [122, 115, 102] as Rgb255,  // warm slate (was 0.48,0.45,0.40)
    /** shadowDistance = clamp(worldRadius + margin, min, max). The margin
     *  approximates the orbit camera's distance from the world edge; max
     *  must cover the largest org (orchard cap 70u + housing reach ≈ 140u
     *  + camera ~100u opposite → ~240u). */
    shadowMargin: 130,
    shadowDistanceMin: 150,
    shadowDistanceMax: 240,
  },

  GROUND: {
    /** Diffuse multiplier over grass.jpg — lifts the olive base toward
     *  vibrant spring green (red suppressed, green slightly over 1). */
    tint: [0.74, 1.04, 0.52] as readonly [number, number, number],
    gloss: 0.05,
    /** Procedural fallback texture base. */
    base: [58, 118, 38] as Rgb255,
    /** Path-wear halo strips (GrassDressing). */
    wear: [158, 132, 95] as Rgb255,
    wearTint: [0.62, 0.52, 0.38] as readonly [number, number, number],
  },

  /** Sand/dirt disc overlays at building zones (GroundSystem). */
  ZONE_COLORS: {
    pool:       [218, 192, 142] as Rgb255,  // warm sand
    housing:    [198, 176, 132] as Rgb255,  // sandy dirt
    coffee_bar: [172, 148, 112] as Rgb255,  // packed earth
    cafeteria:  [176, 152, 118] as Rgb255,  // packed earth
    pavilion:   [178, 172, 158] as Rgb255,  // stone paving
  } as Record<string, Rgb255>,

  /**
   * Repo-tree trunk identity palette — one distinct hue per repo, cycled
   * by index. Curated muted-jewel + natural-wood set: hues stay spread
   * around the wheel for identity, but saturation/lightness are capped so
   * the orchard reads cohesive instead of neon.
   * NOTE: trunk color is part of the IndexedDB tree-cache key — changing
   * an entry forces a one-time regrow of that tree.
   */
  TRUNK_PALETTE: [
    [139, 94, 60],    // walnut
    [193, 112, 62],   // terracotta
    [108, 134, 196],  // slate blue
    [82, 152, 134],   // sea green
    [186, 110, 120],  // dusty rose
    [158, 146, 72],   // olive gold
    [128, 104, 168],  // heather violet
    [196, 150, 88],   // honey oak
    [104, 148, 88],   // moss
    [168, 98, 138],   // plum
    [88, 144, 168],   // steel teal
    [172, 132, 96],   // chestnut
  ] as Rgb255[],

  /** Procedural repo-tree leaves (LeafSystem). Leaf color = trunk color
   *  blended into `base` by `blendTrunk`; `emissiveScale` lifts shadowed
   *  canopies without the old neon glow (was 0.65). */
  LEAF: {
    base: [76, 158, 60] as Rgb255,
    blendTrunk: 0.3,
    emissiveScale: 0.35,
  },

  /** Scatter foliage tints (multiplied onto cloned GLB materials). */
  SCATTER: {
    pine:  [0.72, 0.95, 0.78] as readonly [number, number, number],  // deep blue-green
    bush:  [0.92, 1.08, 0.78] as readonly [number, number, number],  // fresh leaf green
  },

  CLOUD: {
    opacity: 0.5,
    emissive: [248, 250, 255] as Rgb255,
  },

  POSTFX: {
    bloomIntensity: 0.03,
    grading: { saturation: 1.12, contrast: 1.04, brightness: 1.0 },
    vignette: { intensity: 0.2, inner: 0.6, outer: 1.8, curvature: 0.5 },
  },
} as const
