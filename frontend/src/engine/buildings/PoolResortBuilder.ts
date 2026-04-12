/**
 * PoolResortBuilder — Pool area with procedural water + umbrella chair sets.
 *
 * Uses the existing `WaterSurface` effect for a sunken pool basin with
 * caustic-textured water, surrounded by umbrella+chair GLB sets.
 *
 * Umbrella+Chairs GLB model-space AABB (union of 4 meshes):
 *   X: [-201.36, 159.89]  (size: 361.25, center: -20.74)
 *   Y: [-218.68, 175.50]  (size: 394.17, center: -21.59)
 *   Z: [-153.32, 217.88]  (size: 371.20, center:  32.28)
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
import { SeatProber } from "../characters/SeatProber";

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

// ─── Umbrella+Chairs known constants ───

/** Model-space X extent (union of 4 meshes). */
const UC_NATIVE_WIDTH = 361.25;

/** Model-space AABB center (model is NOT centered at origin). */
const UC_CENTER_X = -20.74;
const UC_CENTER_Z = 32.28;

/** Model-space Y minimum (bottom of chair legs). */
const UC_Y_MIN = -218.68;

/** Desired world-space width of each umbrella+chair set. */
const UC_TARGET_WIDTH = 2.5;

/** Uniform scale for umbrella+chair instances. */
const UC_SCALE = UC_TARGET_WIDTH / UC_NATIVE_WIDTH; // ≈ 0.00692

export class PoolResortBuilder {
  private loader: AssetLoader;
  private materials: MaterialFactory | null;

  constructor(factory: BuildingFactory, loader: AssetLoader) {
    this.loader = loader;
    this.materials = factory.materialFactory;
  }

  /**
   * Place a scaled, centered umbrella+chair set as a child of parent.
   * Uses known constants for centering — no runtime AABB measurement.
   */
  private placeUmbrellaSet(
    parent: pc.Entity,
    ucAsset: pc.Asset,
    localX: number,
    localY: number,
    localZ: number,
    yaw = 0,
  ): pc.Entity {
    const model = this.loader.instance(ucAsset);
    model.setLocalScale(UC_SCALE, UC_SCALE, UC_SCALE);
    model.setLocalPosition(
      -UC_CENTER_X * UC_SCALE,
      -UC_Y_MIN * UC_SCALE,
      -UC_CENTER_Z * UC_SCALE,
    );

    const wrapper = new pc.Entity("UmbrellaChairs");
    wrapper.addChild(model);
    wrapper.setLocalPosition(localX, localY, localZ);
    if (yaw !== 0) wrapper.setLocalEulerAngles(0, yaw, 0);
    parent.addChild(wrapper);
    return wrapper;
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

    // ─── Procedural water body (replaces pond.glb) ───
    // WaterSurface creates a sunken basin with walls + translucent caustic
    // water plane. The pool sits below ground level so the water surface
    // shimmers at Y ≈ 0.15.
    const waterSurface = new WaterSurface();
    waterSurface.build(app, this.materials!, {
      x, z,
      width: POOL_WIDTH,
      depth: POOL_DEPTH,
    });

    // ─── Umbrella + Chair sets around the pool ───
    // Chairs sit at ground level (Y=0) since the pond terrain is gone.
    const ucAsset = await this.loader.load(POOL.umbrellaChairs);
    const chairY = 0;

    // Helper: place umbrella set + probe seat surface from mesh geometry
    const placeAndProbe = (localX: number, localZ: number, yaw: number) => {
      const wrapper = this.placeUmbrellaSet(root, ucAsset, localX, chairY, localZ, yaw);
      const probedY = SeatProber.probeSeatY(wrapper);
      seats.push(
        BuildingFactory.createInteractionSeat(
          'pool_resort', seatIndex++,
          x + localX, z + localZ, yaw, 'poolChair', 'sit', chairY, probedY ?? undefined,
        ),
      );
    };

    // Left side: 2 sets facing pool (+X → yaw 90)
    placeAndProbe(-5.0, -1.5, 90);
    placeAndProbe(-5.0, 2.5, 90);

    // Right side: 2 sets facing pool (-X → yaw -90)
    placeAndProbe(5.0, -1.5, -90);
    placeAndProbe(5.0, 2.5, -90);

    // Far end: 2 sets facing pool (toward -Z → yaw 180)
    placeAndProbe(-2.5, 5.0, 180);
    placeAndProbe(2.5, 5.0, 180);

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
