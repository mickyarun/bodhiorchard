/**
 * PoolResortBuilder — Pool area with procedural water + individual deck chairs.
 *
 * Uses the `WaterSurface` effect for a sunken pool basin with caustic-
 * textured water, surrounded by individual `deck_chair.glb` chairs
 * placed via `BuildingFactory.placeSeat()` — the same pattern used by
 * CoffeeBarBuilder and CafeteriaBuilder for precise SeatProber-calibrated
 * seating.
 */
import * as pc from "playcanvas";
import type { Application } from "../core/Application";
import { BuildingFactory } from "./BuildingFactory";
import { POOL } from "../assets/AssetManifest";
import type { AssetLoader } from "../assets/AssetLoader";
import type { MaterialFactory } from "../rendering/MaterialFactory";
import type { InteractionPoint } from "../characters/InteractionPoint";
import type { ExclusionZone } from "../utils/MathUtils";
import { WaterSurface } from "../effects/WaterSurface";

export interface PoolResortResult {
  entity: pc.Entity;
  exclusionZone: ExclusionZone;
  seats: InteractionPoint[];
  /** Pond obstacle for takeover physics (player blocked from entering water). */
  pondObstacle: { x: number; z: number; radius: number };
  /** Water surface effect — caller must call update(dt) each frame. */
  waterSurface: WaterSurface;
}

// ─── Pool dimensions ───

/** World-space width/depth of the water body. */
const POOL_WIDTH = 6;
const POOL_DEPTH = 6;

export class PoolResortBuilder {
  private factory: BuildingFactory;
  private materials: MaterialFactory | null;

  constructor(factory: BuildingFactory, _loader: AssetLoader) {
    this.factory = factory;
    this.materials = factory.materialFactory;
  }

  async build(
    app: Application,
    x: number,
    z: number,
  ): Promise<PoolResortResult> {
    const root = new pc.Entity("PoolResort");
    root.setPosition(x, 0, z);

    const seats: InteractionPoint[] = [];
    let seatIndex = 0;

    // ─── Procedural water body ───
    const waterSurface = new WaterSurface();
    waterSurface.build(app, this.materials!, {
      x, z,
      width: POOL_WIDTH,
      depth: POOL_DEPTH,
    });

    // ─── Individual deck chairs around the pool ───
    // Each chair is placed via placeSeat (same pattern as cafeteria benches)
    // so SeatProber detects the correct seat surface from the mesh geometry.
    // 6 chairs: 2 left, 2 right, 2 far end — each facing the pool.

    const chairPositions: Array<{ lx: number; lz: number; yaw: number }> = [
      // Left side: facing pool (+X → yaw 90)
      { lx: -5.0, lz: -1.5, yaw: 90 },
      { lx: -5.0, lz: 2.5,  yaw: 90 },
      // Right side: facing pool (-X → yaw -90)
      { lx: 5.0,  lz: -1.5, yaw: -90 },
      { lx: 5.0,  lz: 2.5,  yaw: -90 },
      // Far end: facing pool (-Z → yaw 180)
      { lx: -2.5, lz: 5.0,  yaw: 180 },
      { lx: 2.5,  lz: 5.0,  yaw: 180 },
    ];

    for (const pos of chairPositions) {
      const result = await this.factory.placeSeat(
        root,
        POOL.deckChair,
        pos.lx,
        pos.lz,
        pos.yaw,
        'pool_resort',
        seatIndex++,
        x, z,
        'deckChair',
        'sit',
      );
      seats.push(result.seat);
    }

    app.root.addChild(root);

    return {
      entity: root,
      exclusionZone: { x, z, radius: 14 },
      seats,
      pondObstacle: { x, z, radius: POOL_WIDTH / 2 + 0.5 },
      waterSurface,
    };
  }
}
