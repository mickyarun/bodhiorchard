/**
 * PoolResortBuilder — Pond with surrounding umbrella + chair sets.
 *
 * Uses "Pond by jeremy [CC-BY] via Poly Pizza" GLB as the centerpiece,
 * with "Umbrella and chairs" GLB sets arranged around it.
 *
 * Follows the HouseBuilder known-constants pattern: all models were
 * measured ONCE and dimensions are recorded as constants.
 * No dynamic AABB measurement, no syncHierarchy, no scene-graph tricks.
 *
 * Pond GLB model-space AABB (union of 6 meshes):
 *   X: [-99.75, 99.75]  (size: 199.5, centered at origin)
 *   Y: [  0.50, 74.36]  (size: 73.87, bottom is dirt base)
 *   Z: [-99.75, 99.75]  (size: 199.5, centered at origin)
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
import type { InteractionPoint } from "../characters/InteractionPoint";
import type { ExclusionZone } from "../utils/MathUtils";

export interface PoolResortResult {
  entity: pc.Entity;
  exclusionZone: ExclusionZone;
  seats: InteractionPoint[];
}

// ─── Pond known constants ───

/** Model-space X extent (union of all 6 meshes). XZ-symmetric, centered at origin. */
const POND_NATIVE_WIDTH = 199.5;

/** Desired world-space width of the pond. */
const TARGET_POND_WIDTH = 14;

/** Uniform scale to apply to the pond entity. */
const POND_SCALE = TARGET_POND_WIDTH / POND_NATIVE_WIDTH; // ≈ 0.04010

/**
 * Y offset for the pond entity — sinks the dirt base below the ground plane
 * while keeping the water surface visible. The pond GLB includes its own
 * water mesh, so we must not push too far or the water goes underground.
 */
const POND_Y_OFFSET = -0.15;

/**
 * Grass surface Y in world units — the flat area where furniture sits.
 * This is the Y coordinate (relative to root) at which umbrella+chair
 * sets should be placed.
 */
const POND_SURFACE_Y = 0.18;

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

  constructor(_factory: BuildingFactory, loader: AssetLoader) {
    this.loader = loader;
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
  ): void {
    const model = this.loader.instance(ucAsset);
    model.setLocalScale(UC_SCALE, UC_SCALE, UC_SCALE);

    // Center the model: offset so XZ center + Y bottom align with wrapper origin.
    // In wrapper space: vertex at model(vx, vy, vz) → (ox + vx*s, oy + vy*s, oz + vz*s)
    // Center XZ: ox = -centerX * scale, oz = -centerZ * scale
    // Bottom Y=0: oy = -yMin * scale
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

    // ─── Pond GLB (centerpiece) ───
    const pondAsset = await this.loader.load(POOL.pond);
    const pond = this.loader.instance(pondAsset);
    pond.setLocalScale(POND_SCALE, POND_SCALE, POND_SCALE);
    pond.setLocalPosition(0, POND_Y_OFFSET, 0);
    root.addChild(pond);

    // ─── Umbrella + Chair sets around the pond ───
    const ucAsset = await this.loader.load(POOL.umbrellaChairs);

    // Left side: 2 sets facing pond (+X → yaw 90)
    const leftX = -5.0;
    this.placeUmbrellaSet(root, ucAsset, leftX, POND_SURFACE_Y, -1.5, 90);
    seats.push(
      BuildingFactory.createInteractionSeat(
        'pool_resort', seatIndex++,
        x + leftX, z - 1.5, 90, 'poolChair', 'sit', POND_SURFACE_Y,
      ),
    );
    this.placeUmbrellaSet(root, ucAsset, leftX, POND_SURFACE_Y, 2.5, 90);
    seats.push(
      BuildingFactory.createInteractionSeat(
        'pool_resort', seatIndex++,
        x + leftX, z + 2.5, 90, 'poolChair', 'sit', POND_SURFACE_Y,
      ),
    );

    // Right side: 2 sets facing pond (-X → yaw -90)
    const rightX = 5.0;
    this.placeUmbrellaSet(root, ucAsset, rightX, POND_SURFACE_Y, -1.5, -90);
    seats.push(
      BuildingFactory.createInteractionSeat(
        'pool_resort', seatIndex++,
        x + rightX, z - 1.5, -90, 'poolChair', 'sit', POND_SURFACE_Y,
      ),
    );
    this.placeUmbrellaSet(root, ucAsset, rightX, POND_SURFACE_Y, 2.5, -90);
    seats.push(
      BuildingFactory.createInteractionSeat(
        'pool_resort', seatIndex++,
        x + rightX, z + 2.5, -90, 'poolChair', 'sit', POND_SURFACE_Y,
      ),
    );

    // Far end: 2 sets facing pond (toward -Z → yaw 180)
    const farZ = 5.0;
    this.placeUmbrellaSet(root, ucAsset, -2.5, POND_SURFACE_Y, farZ, 180);
    seats.push(
      BuildingFactory.createInteractionSeat(
        'pool_resort', seatIndex++,
        x - 2.5, z + farZ, 180, 'poolChair', 'sit', POND_SURFACE_Y,
      ),
    );
    this.placeUmbrellaSet(root, ucAsset, 2.5, POND_SURFACE_Y, farZ, 180);
    seats.push(
      BuildingFactory.createInteractionSeat(
        'pool_resort', seatIndex++,
        x + 2.5, z + farZ, 180, 'poolChair', 'sit', POND_SURFACE_Y,
      ),
    );

    // Add to scene at END — matches all other builders
    app.root.addChild(root);

    return {
      entity: root,
      exclusionZone: { x, z, radius: 14 },
      seats,
    };
  }
}
