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
    /** 50° flattens low-poly forms slightly vs the old 55° without the
     *  telephoto compression a 45° FOV showed at this orbit distance. */
    fov: 50,
  },

  LIGHT: {
    sun:          [255, 230, 189] as Rgb255,  // warm golden
    sunIntensity: 2.1,
    /** Shadows never crush to black — big repo-tree canopies otherwise
     *  paint dead-dark wedges across the grass carpet. */
    shadowIntensity: 0.78,
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
    tint: [0.80, 1.06, 0.52] as readonly [number, number, number],
    /** grass.jpg tiles across the 600u plane. Fewer tiles = larger, softer
     *  painterly patches; the fine 60×60 noise fought the blade carpet. */
    tiling: 34,
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

  /** Natural bark for repo-tree trunks/branches. The per-repo IDENTITY
   *  color lives in the canopy (LEAF.blendTrunk) and feature branches —
   *  wooden trunks with tinted crowns read as real trees instead of
   *  candy-colored skeletons. */
  TREE_BARK: {
    root: [96, 66, 42] as Rgb255,
  },

  /**
   * Repo-tree identity palette — one distinct hue per repo, cycled by
   * index. Expressed in the CANOPY (leaf blend) and feature branches,
   * not the trunk. Curated muted-jewel + natural-wood set: hues stay
   * spread around the wheel for identity, saturation/lightness capped.
   * NOTE: the palette index is part of the IndexedDB tree-cache key.
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

  /** Procedural repo-tree leaves (LeafSystem). Leaf color = the repo's
   *  IDENTITY color blended into `base` by `blendTrunk` — with wooden
   *  trunks, the canopy is where per-repo identity reads. `emissiveScale`
   *  lifts shadowed canopies without the old neon glow (was 0.65). */
  LEAF: {
    base: [76, 158, 60] as Rgb255,
    blendTrunk: 0.55,
    emissiveScale: 0.35,
  },

  /** Procedural grass carpet (GrassSystem). The reference look is a dense
   *  painterly field where blades and ground read as ONE surface: roots
   *  sit at the ground color, tips go warm yellow-green. Three batch tints
   *  give large-scale patch variation without per-instance color data. */
  GRASS_BLADES: {
    root: [46, 100, 32] as Rgb255,   // ≈ ground color (blades grow out of it)
    tip:  [112, 182, 70] as Rgb255,  // sunlit tip — green-leaning, yellow only as a hint
    batchTints: [
      [1.0, 1.0, 1.0],
      [0.85, 0.92, 0.82],
      [1.03, 1.02, 0.93],
    ] as ReadonlyArray<readonly [number, number, number]>,
  },

  /** Procedural flower tufts dotted through the carpet (GrassSystem).
   *  Petal color per batch; stems stay grass-green. */
  FLOWERS: {
    stem: [74, 128, 52] as Rgb255,
    petals: [
      [252, 250, 240] as Rgb255,  // daisy white
      [248, 142, 128] as Rgb255,  // soft coral
      [250, 214, 110] as Rgb255,  // buttercup
    ],
  },

  /** Scatter foliage tints (multiplied onto cloned GLB materials). */
  SCATTER: {
    pine:  [0.72, 0.95, 0.78] as readonly [number, number, number],  // deep blue-green
    bush:  [0.92, 1.08, 0.78] as readonly [number, number, number],  // fresh leaf green
    grass: [0.90, 1.05, 0.78] as readonly [number, number, number],  // spring blades
    /** Warm wood multiplier for the pale Kenney log/stump GLBs — untinted
     *  they render plastic-white in the daylit scene. */
    wood:  [0.84, 0.64, 0.44] as readonly [number, number, number],
    /** Vertex-wind sway amplitude for grass/flower scatter (world units
     *  at blade tip, pre height² weighting). */
    grassWindStrength: 0.35,
  },

  CLOUD: {
    opacity: 0.5,
    emissive: [248, 250, 255] as Rgb255,
  },

  /** Swimming pool (WaterSurface + PoolResortBuilder). Tropical-resort
   *  read: bright aqua water over a light tiled basin — the old navy
   *  basin + 0.7-opacity water collapsed into a flat dark rectangle. */
  POOL: {
    water:        [0.22, 0.66, 0.94] as readonly [number, number, number],
    waterEmissive: [0.08, 0.36, 0.56] as readonly [number, number, number],
    waterOpacity: 0.85,
    causticBase:  [36, 138, 172] as Rgb255,
    /** Light shallow band ringing the water's edge — the classic stylized
     *  pool read (deep center, pale rim). */
    rim:          [168, 226, 246] as Rgb255,
    basinFloor:   [0.30, 0.62, 0.80] as readonly [number, number, number],
    basinWall:    [0.38, 0.70, 0.86] as readonly [number, number, number],
    /** Teak deck planks (two alternating board tones). */
    plankA:       [0.78, 0.60, 0.40] as readonly [number, number, number],
    plankB:       [0.70, 0.52, 0.34] as readonly [number, number, number],
    coping:       [0.97, 0.95, 0.90] as readonly [number, number, number],
  },

  /** Housing village (HouseBuilder / RectangularFence / HousingVillage). */
  VILLAGE: {
    /** Packed-earth floor covering the whole fenced compound — the grass
     *  carpet stops at the fence line; inside is village ground. */
    floor:        [0.66, 0.56, 0.42] as readonly [number, number, number],
    roofClay:     [0.78, 0.46, 0.36] as readonly [number, number, number],
    roofTrim:     [0.92, 0.88, 0.80] as readonly [number, number, number],
    chimney:      [0.62, 0.60, 0.58] as readonly [number, number, number],
    fencePostA:   [0.55, 0.40, 0.24] as readonly [number, number, number],
    fencePostB:   [0.63, 0.48, 0.30] as readonly [number, number, number],
    fencePanel:   [0.68, 0.54, 0.34] as readonly [number, number, number],
    fenceGate:    [0.42, 0.30, 0.16] as readonly [number, number, number],
  },

  /** Paths, village roads, and lanterns. */
  PATHS: {
    /** Packed-earth texture base (PathSystem.createSandTexture). */
    surfaceBase:   [186, 170, 142] as Rgb255,
    /** Primary path tint — calm sand; the old warm tint glowed orange
     *  once grading saturation stacked on it. */
    primaryTint:   [0.94, 0.90, 0.82] as readonly [number, number, number],
    secondaryTint: [0.66, 0.57, 0.46] as readonly [number, number, number],
    /** Path-wear halo peak alpha — subtle tint, not a glow strip. */
    wearAlpha: 0.5,
    lanternPole:   [0.34, 0.23, 0.14] as readonly [number, number, number],
    lanternGlow:   [1.0, 0.87, 0.45] as readonly [number, number, number],
    lanternPoleWidth: 0.09,
  },

  POSTFX: {
    bloomIntensity: 0.018,
    grading: { saturation: 1.07, contrast: 1.03, brightness: 1.0 },
    vignette: { intensity: 0.2, inner: 0.6, outer: 1.8, curvature: 0.5 },
  },
} as const
