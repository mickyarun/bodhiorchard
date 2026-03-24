# Garden Engine — Architecture Reference

## Overview

The Garden Engine is a 3D visualization built on **PlayCanvas v2.17.2** that renders
software repositories as a living garden world. Members appear as characters, repos
become trees, and buildings represent team activities.

This document is the **single source of truth** for how the engine is structured.
Every file, every data flow, every design decision is documented here.

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| 3D Runtime | PlayCanvas v2.17.2 | WebGL rendering, scene graph, materials |
| Language | TypeScript (strict) | All engine code |
| Host Framework | Vue 3 + Vite | The engine is embedded in a Vue component |
| Shaders | GLSL ES 1.0 | Custom sky, water, ground, wind effects |
| Models | GLTF/GLB | Character models (Quaternius library), garden assets |

---

## Critical Design Decision: PBR Lighting Pipeline

**The #1 thing to understand about this rewrite.**

The OLD engine had a fatal flaw: every material used `useLighting = false` and piped
colors through `emissive` instead of `diffuse`. This was a workaround for missing IBL
(Image-Based Lighting), but it made all GLTF models render **black** because:
- GLTF stores colors in LINEAR color space
- Without proper gamma correction, LINEAR colors appear too dark
- Without an environment cubemap, metallic/glossy materials have nothing to reflect

The NEW engine fixes this at the root in `Application.ts`:
```
scene.toneMapping = TONEMAP_ACES    // Filmic tone mapping
scene.gammaCorrection = GAMMA_SRGB  // Proper LINEAR → sRGB conversion
scene.exposure = 1.2                // Bright outdoor scene
setupIBL()                          // Procedural cubemap for reflections
```

**Rule: NEVER use `useLighting = false` in any new code.** If a material looks wrong,
the fix is adjusting the IBL/exposure/material properties — not bypassing the pipeline.

---

## Directory Structure

```
frontend/src/engine/
│
├── index.ts                    # GardenEngine — THE public API (only Vue import)
├── types.ts                    # All type definitions (zero external imports)
├── ARCHITECTURE.md             # This file
│
├── core/                       # Engine fundamentals
│   ├── Application.ts          # PlayCanvas bootstrap, lighting, frame loop
│   ├── Clock.ts                # Delta time + elapsed tracking
│   ├── EventBus.ts             # Typed pub/sub for decoupled communication
│   └── SceneManager.ts         # [Phase 2] Orchestrates building full scene
│
├── input/
│   └── InputManager.ts         # Keyboard, mouse, touch input
│
├── camera/
│   └── CameraController.ts     # Third-person orbit camera (overview + follow)
│
├── rendering/
│   ├── MaterialFactory.ts      # Centralized PBR material creation + cache
│   └── LabelRenderer.ts        # [Phase 3] Billboard name labels
│
├── utils/
│   ├── MathUtils.ts            # Easing, noise, hash, clamp, lerp, grid layout
│   └── EntityUtils.ts          # Entity/material cleanup helpers
│
├── shaders/                    # GLSL shader source files
│   ├── sky.vert / sky.frag     # Sky sphere gradient + sun disc
│   ├── ground.vert / ground.frag   # Ground grass/dirt blend
│   ├── water.vert / water.frag # Water surface waves + caustics
│   └── wind.vert               # Wind displacement (stub for grass)
│
├── environment/                # [Phase 2] Natural world
│   ├── SkySystem.ts            # Procedural sky sphere
│   ├── GroundSystem.ts         # Textured terrain
│   ├── GrassSystem.ts          # Instanced grass + flowers
│   ├── RockSystem.ts           # GLB rocks
│   └── CloudSystem.ts          # Cloud billboard planes
│
├── world/                      # [Phase 2] Repo visualization
│   ├── WorldLayout.ts          # Zone placement + exclusion
│   ├── TreeBuilder.ts          # Single tree mesh construction
│   ├── TreeDecorator.ts        # Fruits, flowers, bugs on trees
│   ├── TreeSystem.ts           # Orchestrator for all trees
│   └── RelationshipArcs.ts     # Bezier arcs between trees
│
├── buildings/                  # [Phase 2] Activity buildings
│   ├── BuildingFactory.ts      # Shared primitives helper
│   ├── HouseBuilder.ts         # Single house
│   ├── HousingVillage.ts       # Grid of houses
│   ├── CoffeeBarBuilder.ts     # Coffee bar + seats
│   ├── CafeteriaBuilder.ts     # Lunch building + seats
│   ├── StandupPavilion.ts      # Meeting area
│   └── PoolResortBuilder.ts    # Pool + chairs + floats
│
├── effects/                    # [Phase 2+] Visual effects
│   ├── WaterSurface.ts         # Shader-based pool water
│   ├── StringLightEffect.ts    # Decorative lights
│   ├── ParticleEmitter.ts      # [Phase 6] Generic particles
│   ├── SplashEffect.ts         # [Phase 6] Pool splashes
│   ├── ZzzEffect.ts            # [Phase 6] Sleep particles
│   └── SteamEffect.ts          # [Phase 6] Coffee/cooking steam
│
├── assets/                     # [Phase 3] Asset loading
│   ├── AssetLoader.ts          # GLTF/GLB load + cache + dedup
│   └── CharacterCatalog.ts     # Model lists, hash-based assignment
│
├── characters/                 # [Phase 3] Character system
│   ├── CharacterFactory.ts     # Load, clone, proper PBR materials
│   ├── AnimationController.ts  # State machine (idle/walk/run/swim/sit)
│   ├── CharacterEntity.ts      # Mesh + animator + name label
│   ├── PlayerController.ts     # WASD movement + swimming
│   └── PropAttachment.ts       # Watering can, fertilizer, agent gear
│
├── ai/                         # [Phase 4] NPC behaviors
│   ├── BehaviorTree.ts         # Generic BT evaluator
│   ├── BehaviorNodes.ts        # Selector, Sequence, etc.
│   ├── NPCDirector.ts          # Assigns behaviors based on time + presence
│   └── behaviors/              # Individual behavior implementations
│
├── time/                       # [Phase 4] Time-based scheduling
│   ├── TimeScheduler.ts        # Day/hour → activity mapping
│   └── ActivityRules.ts        # Presence + time → behavior
│
├── interaction/                # [Phase 5] Click/hover
│   ├── PickerSystem.ts         # Ray-sphere picking
│   ├── TooltipManager.ts       # Tooltip content generation
│   └── FocusSystem.ts          # Camera focus on click
│
└── vehicles/                   # [Phase 6] Agent vehicles
    ├── VehicleBuilder.ts       # Procedural meshes
    └── VehicleSystem.ts        # Arrival animations
```

---

## Data Flow

This is how data moves from the Vue app into the 3D scene:

```
Vue Component (PlayCanvasCanvas.vue)
  │
  │  adaptTreeData(TreeData) → EngineData
  │
  ▼
GardenEngine (index.ts)           ◄── THE boundary. Only public API.
  │
  ├── init(container, w, h)       Creates Application, Input, Camera
  │     │
  │     └── Application.ts        Boots PlayCanvas, sets up PBR lighting
  │           ├── Procedural IBL cubemap (sky gradient)
  │           ├── ACES tone mapping + sRGB gamma
  │           ├── Sun directional light + fill light
  │           └── Frame loop → calls onUpdate each frame
  │
  ├── setData(data)               [Phase 2+] Delegates to SceneManager
  │     │
  │     └── SceneManager          Orchestrates full scene build:
  │           ├── TreeSystem       → trees from repos
  │           ├── Buildings        → coffee bar, cafeteria, houses, pool
  │           ├── Environment      → sky, ground, grass, rocks, clouds
  │           ├── Characters       → player + NPCs
  │           └── Effects          → water, particles, lights
  │
  └── onUpdate(dt)                Per-frame: camera, animations, effects
```

**Key rule:** `types.ts` has ZERO imports from the app layer (`@/stores`, `@/types`, etc.).
The Vue component's `adaptTreeData()` function is the ONLY adapter between app types and engine types.

---

## Phase 1 Files — Detailed Breakdown

### `index.ts` — GardenEngine

The **only class the Vue layer imports**. Manages lifecycle:
- `init()` — creates canvas, boots Application, sets up Input + Camera
- `setData()` — receives data, will delegate to SceneManager in Phase 2
- `resize()` — forwards to Application
- `destroy()` — tears down everything in reverse order

Design: thin orchestrator. Business logic lives in subsystems.

### `core/Application.ts` — PlayCanvas Bootstrap

Creates and configures the `pc.Application`:
1. **Canvas setup** — antialias, pixel ratio cap at 2x, fill mode
2. **PBR lighting** — ACES tone mapping, sRGB gamma, exposure 1.2
3. **IBL cubemap** — 64x64 procedural cubemap with sky gradient colors
4. **Lights** — sun (1.8 intensity, shadows) + fill sky (0.6, no shadows)
5. **Camera entity** — 55° FOV, 0.5-2000 clip range
6. **Frame loop** — `app.on('update')` drives Clock + billboard rotation

The `setupIBL()` method generates a cubemap by computing sky-gradient colors
for each texel direction on all 6 cube faces. This gives GLTF models something
to reflect, which is why metallic materials stop being black.

### `core/EventBus.ts` — Type-Safe Pub/Sub

Generic event bus parameterized on an event map interface. TypeScript enforces
correct event names and payload types at compile time:

```ts
const bus = new EventBus<EngineEvents>()
bus.emit('scene:ready')                    // OK — void payload
bus.emit('scene:resize', { width: 100, height: 200 })  // OK
bus.emit('scene:readyy')                   // TS ERROR — typo caught!
bus.emit('scene:resize', 'wrong')          // TS ERROR — wrong payload type!
```

Used instead of direct references between subsystems.

### `core/Clock.ts` — Time

Tracks `dt` (seconds since last frame), `elapsed` (total seconds), `frame` (count).
Updated once per frame by Application. Consumed by animated subsystems.

### `input/InputManager.ts` — Input

Wraps PlayCanvas input devices. Key design choices:
- **Click vs Drag discrimination** — 5px threshold + 300ms max for clicks
- **Touch split** — left half = virtual joystick, right half = camera orbit
- **Consumed-on-read** — `getOrbitDelta()` / `getScrollDelta()` reset after reading
- All mouse buttons trigger orbit (not just middle/right)

### `camera/CameraController.ts` — Camera

Two modes:
- **Overview** — free orbit around a static point (initial view)
- **Play** — follows a player entity with smooth lerp (0.08 factor)

Orbit mechanics: yaw (horizontal) + pitch (5°-80°) + distance (5-200).
Smooth transitions between modes using `easeOutCubic` interpolation.

Safety features:
- **Lost target recovery** — if follow target entity is destroyed or disabled, camera auto-falls back to overview mode with NaN guard
- **Transition interruption** — new transitions pick up from current position (not original start), preventing jarring snaps when user clicks rapidly

### `rendering/MaterialFactory.ts` — Materials

Centralized material creation with reference-counted cache + LRU eviction.
- `getColor(key, r, g, b, opts)` — PBR material (diffuse color, metalness, gloss)
- `createShaderMaterial(app, vs, fs, attrs)` — custom shader material
- `release(key)` — decrement refcount, destroy at zero
- **Max cache size: 256** — when full, evicts least-recently-used material with refCount=0

**Critical:** all materials created here use `useLighting = true` (the default).
This works because Application.ts sets up proper IBL + tone mapping.

### `utils/MathUtils.ts` — Math

Pure functions, no PlayCanvas imports:
- Easing: `easeOutCubic`, `easeInOutCubic`, `easeOutQuad`
- `hashString(s)` — deterministic string→int (for consistent model assignment)
- `simplexNoise2D(x, y)` — fake simplex for procedural scatter
- `clamp`, `lerp`, `randRange` — numeric utilities
- `isInsideAnyZone(px, pz, zones)` — circular exclusion check
- `gridPosition(i, cols, spacingX, spacingZ)` — grid layout helper

### `utils/EntityUtils.ts` — Cleanup

PlayCanvas entity/material destruction helpers:
- `destroyEntity(entity)` — recursive destroy
- `clearChildren(entity)` — destroy all children
- `disposeMaterial(material)` — destroy material + all texture maps

### `types.ts` — Data Contract

Self-contained type definitions (ZERO external imports). Defines:
- **Data types**: EngineRepoData, EngineBranchData, EngineLeafData, EngineFeature, EngineBUD, EngineThreat, EngineMember, EngineRelationship
- **Top-level contract**: `EngineData` (what `setData()` receives)
- **Callback types**: EngineCallbacks, EngineTreeInfo, EngineCharacterInfo, EngineHouseInfo
- **Event types**: EngineEvents (for EventBus typing)
- **Enums**: RepoHealth, ThreatSeverity, BUDStatus, ActivityState, etc.

### `shaders/` — GLSL

Copied from old engine, activated in Phase 2:
- `sky.vert/frag` — gradient + sun disc + halo
- `ground.vert/frag` — grass/dirt noise blend
- `water.vert/frag` — dual sine wave displacement + caustic shimmer
- `wind.vert` — stub for grass sway (commented out)

---

## Sky Rendering Strategy

The engine uses a **two-layer sky system**:

### Layer 1: Visual Sky (SkySystem — Phase 2)

A large inverted sphere with a **Preetham atmospheric scattering shader**.
This renders at full screen resolution and produces physically-based sky colors.

**How it works:** The Preetham model is a math formula that computes real atmospheric
light scattering. Given a sun position and turbidity (haze level), it produces:
- Blue noon sky
- Orange/pink sunset
- Dark blue night sky
- Sun disc with halo

**Day/night support:** Just move the `sunPosition` uniform. The shader naturally
transitions through all times of day. When the sun dips below the horizon,
the sky darkens to night. Pair with changes to directional light intensity/color
and fog color for a complete day/night cycle.

**Implementation:** Custom GLSL shader on StandardMaterial (our `sky.frag` already
has the sun disc + gradient foundation — Phase 2 extends it with Preetham coefficients).

### Layer 2: IBL Cubemap (Application.ts)

A low-resolution (128x128) procedural cubemap for Image-Based Lighting.
This is invisible — it only affects how materials shade and reflect.

**Why separate:** The visual sky renders at screen resolution (sharp), but IBL
needs a cubemap texture (for reflections). Regenerating a 128x128 cubemap is cheap
enough to do every few seconds when time-of-day changes.

**API for day/night IBL updates:**
```ts
application.updateIBL((dir) => {
  // Return [r, g, b] (0-255) for this direction
  // SkySystem provides the color function based on current time
  return computePreethamColor(dir, sunPosition, turbidity)
})
```

---

## Conventions

1. **No `useLighting = false`** — ever. Fix lighting at the scene level.
2. **Self-contained types** — `types.ts` has zero app-layer imports.
3. **Single entry point** — Vue only imports `GardenEngine` from `index.ts`.
4. **Exclusion zones** — buildings/trees return `{ x, z, radius }` zones; grass/rocks avoid them.
5. **Deterministic hashing** — same `user_id` always gets same character model via `hashString()`.
6. **Billboard registry** — use `app.registerBillboard(entity)` / `unregisterBillboard(entity)` for labels that face the camera. Do NOT use `findByTag('billboard')` (it's O(n) on the entire scene graph every frame).
7. **Material caching** — use `MaterialFactory.getColor(key, ...)` to avoid duplicate materials. Cache has LRU eviction at 256 entries.
8. **Cleanup order** — destroy subsystems in reverse creation order.
9. **Camera safety** — if a follow target is destroyed, the camera auto-falls back to overview mode.
10. **Type-safe events** — `EventBus<EngineEvents>` enforces event names and payload types at compile time.

---

## How to Add a New Subsystem (Phase 2+)

1. Create the file in the appropriate directory (e.g., `environment/SkySystem.ts`)
2. The class should:
   - Accept `pc.AppBase` in constructor (for asset loading, entity creation)
   - Expose an `entity: pc.Entity` (added to scene graph)
   - Have `build()`, `update(dt)`, `destroy()` methods
   - Return exclusion zones if it occupies ground space
3. Wire it into `SceneManager.ts` (Phase 2) or directly into `GardenEngine`
4. Add update call in `GardenEngine.onUpdate()`

---

## Asset Catalog (Kenney Packs)

All 3D assets are Kenney low-poly GLB models. They're pre-lit friendly (solid colors, no textures needed)
and work perfectly with the PBR pipeline.

### Characters — `/characters/` (Kenney Blocky Characters)

18 models: `character-a.glb` through `character-r.glb` (~110KB each)

Each model has **27 named animations** (identical across all 18):
`static`, `idle`, `walk`, `sprint`, `sit`, `drive`, `die`, `pick-up`,
`emote-yes`, `emote-no`, `holding-right`, `holding-left`, `holding-both`,
`attack-melee-right`, `attack-melee-left`, `attack-kick-right`, `attack-kick-left`,
`interact-right`, `interact-left`, `wheelchair-idle`, `wheelchair-forward`,
`wheelchair-backward`, `wheelchair-right`, `wheelchair-left`, `carrying`, `pushbutton`, `typing`

**Assignment:** `hashString(userId) % 18` → deterministic, consistent character per member.

### Nature — `/assets/garden/` (Kenney Nature Kit)

| Category | Models |
|----------|--------|
| Trees | `tree_oak`, `tree_detailed`, `tree_fat`, `tree_default`, `tree_tall`, `tree_cone`, `tree_simple`, `tree_blocks`, `tree_plateau`, `tree_thin` + `_fall`/`_dark` variants |
| Flowers | `flower_purpleA/B/C`, `flower_redA/B/C`, `flower_yellowA/B/C` (9 total) |
| Grass | `grass.glb`, `grass_large.glb`, `grass_leafs.glb` |
| Bushes | `plant_bush`, `plant_bushSmall`, `plant_bushLarge` |
| Rocks | `rock_smallA/B/C`, `rock_largeA/B`, `rock_tallA/B`, `stone_smallA/B` |
| Props | `mushroom_red/tan`, `log`, `log_stack`, `stump_round/old`, `campfire_logs/stones`, `lily_large/small`, `path_stone`, `fence_simple` |

### Furniture — `/assets/furniture/` (Kenney Furniture Kit)

| Zone | Models |
|------|--------|
| Coffee Bar | `chair`, `chairCushion`, `table`, `tableRound`, `tableCoffee`, `kitchenCoffeeMachine`, `kitchenBar/BarEnd`, `kitchenStove/Sink/Cabinet/Fridge` |
| Cafeteria | `bench`, `benchCushion/CushionLow`, `tableCloth`, `tableCross` |
| Housing | `bedSingle/Double`, `loungeChair`, `loungeSofa`, `cabinetTelevision`, `televisionModern`, `lampRoundFloor/Table`, `rugRound/Rectangle`, `sideTable`, `desk`, `chairDesk`, `laptop`, `books`, `plantSmall1/2`, `pottedPlant` |
| Pool | `loungeChairRelax`, `loungeDesignChair` |
| Structure | `wall`, `wallWindow`, `wallDoorway`, `floorFull`, `doorway`, `stairs` |

---

## Kenney Model Placement — Rules & Conventions

All Kenney Furniture/Nature Kit GLB models share an **origin-at-corner** convention
that requires careful placement. This section documents the measured facts and the
pattern we use to handle them.

### Model Origin Convention

| Fact | Value | Source |
|------|-------|--------|
| Tile size | 1×1 units | Kenney City Builder Starter Kit (`cell_size = Vector3(1,1,1)`) |
| Wall height | 1.29 units | Measured from `wall.glb` AABB (y: 0–1.29) |
| Origin location | Bottom corner | All Kenney models |
| Extension direction | +X and −Z from origin | glTF convention: −Z is forward |

**Floor tiles** (`floorFull.glb`): AABB z = [−1, 0]. The tile extends 1 unit in −Z from its origin.
To tile a floor covering z = [0, depth], place tile origins at z = 1, 2, …, depth (i.e. `(z+1) * TILE_SIZE`).

**Walls** (`wall.glb`): AABB x = [0, 1], z = [−0.05, 0]. Each wall segment is 1 unit wide in +X
and paper-thin in Z. Rotate walls 90°/180°/−90° for the four sides.

**Furniture**: Every piece (bed, desk, chair, sofa, TV…) has its origin at a corner and extends
in +X and −Z. The "interactive face" (seat of a chair, screen of a TV) is at the **origin edge**
(z ≈ 0 side), and the body extends backward into −Z.

### The AABB Centering Pattern (`placeFurnitureCentered`)

Trying to manually offset each model's corner origin is error-prone and fragile.
Instead, we use the **PlayCanvas model-viewer wrapper pattern**:

```
1. Load GLB, create instance
2. Create wrapper Entity at the desired (centerX, y, centerZ) — NO rotation yet
3. Add model as child of wrapper, add wrapper to scene (world transforms now valid)
4. Compute world-space AABB from all MeshInstance.aabb values
5. Offset model so its center-bottom sits at wrapper origin:
     model.setLocalPosition(
       -(aabb.center.x - wrapperPos.x),
       -(aabb.getMin().y - wrapperPos.y),   // bottom on ground
       -(aabb.center.z - wrapperPos.z),
     )
6. Apply yaw rotation AFTER centering (model rotates around visual center)
```

**Critical detail:** Use `MeshInstance.aabb` (world-space), NOT `Mesh.aabb` (local-space).
The entity must be in the scene graph before reading `.aabb`, or the world transform is stale.

### Rotation After Centering

After AABB centering, the model's interactive face (chair seat, TV screen) faces **+Z**.
All yaw angles are relative to this:

| Yaw | Faces | Use when… |
|-----|-------|-----------|
| 0° | +Z | Toward front wall / higher Z |
| 90° | +X | Toward right wall / higher X |
| 180° | −Z | Toward back wall / lower Z |
| −90° | −X | Toward left wall / lower X |

**Circular layouts** (pavilion benches facing center): For a bench at polar angle θ,
the yaw to face center is: `yaw = -90 - θ × 180/π`

### Stacking Items (e.g. laptop on desk, TV on cabinet)

Use `getEntityHeight()` to measure the base item's AABB height, then place the
top item at that Y:

```ts
const desk = await factory.placeFurnitureCentered(root, BUILDING.desk, 3.3, 0, 0.5)
const deskHeight = BuildingFactory.getEntityHeight(desk)
await factory.placeFurnitureCentered(root, BUILDING.laptop, 3.3, deskHeight, 0.5)
```

**Never hardcode heights** — they vary across models and would break if assets change.

**Important:** `getEntityHeight()` uses `Mesh.aabb` (local/model space computed from vertex
data at load time). This is always valid — it does NOT depend on the entity being in the
scene graph or having been rendered. Do NOT use `MeshInstance.aabb` (world-space) for
height measurement, as it requires a render pass to be accurate.

### When to Use Which Method

| Method | Use for |
|--------|---------|
| `placeFurnitureCentered()` | Standalone items: chairs, tables, benches, sofas, TVs, beds — anything that should appear centered at a position |
| `placeFurniture()` | Connected/tiling pieces (bar counter segments), fences, path stones, campfire elements, lily pads — items that connect via their origins |
| `getEntityHeight()` | Measure placed item height for stacking another item on top |

---

## PlayCanvas v2.17 Quirks

- Some `Scene` properties (toneMapping, gammaCorrection, fog*) are not in TS types — cast through `Record<string, unknown>`
- `Material.shader` not typed — cast through `Record<string, unknown>`
- GLTF container assets: `asset.resource.instantiateRenderEntity()` to clone
- Animation component: create with `activate: false`, assign all tracks, then activate — prevents crash on undefined track
- Billboard planes face up by default — `rotateLocal(90, 0, 0)` after `lookAt(camera)` to face correctly
