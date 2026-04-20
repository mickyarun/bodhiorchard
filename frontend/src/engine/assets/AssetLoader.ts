// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * AssetLoader — GLB/GLTF loading with cache + dedup + batch loading.
 *
 * Every subsystem that needs 3D models goes through this loader.
 * Internally deduplicates requests: if two systems request the same
 * GLB simultaneously, only one network fetch occurs.
 *
 * Usage:
 *   const asset = await loader.load('assets/garden/tree_oak.glb')
 *   const entity = loader.instance(asset)
 *   app.root.addChild(entity)
 */
import * as pc from "playcanvas";

export class AssetLoader {
  readonly app: pc.AppBase;
  private cache = new Map<string, pc.Asset>();
  private pending = new Map<string, Promise<pc.Asset>>();

  constructor(app: pc.AppBase) {
    this.app = app;
  }

  /**
   * Load a single GLB/GLTF asset. Returns cached if already loaded.
   * Deduplicates in-flight requests for the same path.
   */
  async load(path: string): Promise<pc.Asset> {
    const cached = this.cache.get(path);
    if (cached) return cached;

    const inflight = this.pending.get(path);
    if (inflight) return inflight;

    const promise = this.loadAsset(path);
    this.pending.set(path, promise);

    try {
      const asset = await promise;
      this.cache.set(path, asset);
      return asset;
    } finally {
      this.pending.delete(path);
    }
  }

  /**
   * Load multiple assets in parallel.
   * Returns assets in the same order as the input paths.
   */
  async loadBatch(paths: string[]): Promise<pc.Asset[]> {
    return Promise.all(paths.map((p) => this.load(p)));
  }

  /**
   * Create a new entity instance from a loaded container asset.
   * Each call returns a fresh clone — safe to position/scale independently.
   */
  instance(asset: pc.Asset): pc.Entity {
    const container = asset.resource as pc.ContainerResource;
    const entity = container.instantiateRenderEntity();

    return entity;
  }

  /** Check if an asset is already cached. */
  has(path: string): boolean {
    return this.cache.has(path);
  }

  /** Clear all cached assets. */
  clear(): void {
    for (const [, asset] of this.cache) {
      asset.unload();
    }
    this.cache.clear();
  }

  private loadAsset(path: string): Promise<pc.Asset> {
    // Anchor relative asset paths at the document root so they resolve the
    // same way regardless of the current route's depth. Without this, a
    // relative path like `assets/foo.glb` resolves against the current URL
    // — fine from `/dashboard` (→ `/assets/foo.glb`) but wrong from
    // `/raceview/abc-123` (→ `/raceview/assets/foo.glb`, which hits the
    // SPA fallback and returns HTML).
    const url = path.startsWith("/") || /^https?:/.test(path) ? path : `/${path}`;
    return new Promise<pc.Asset>((resolve, reject) => {
      const asset = new pc.Asset(path, "container", { url });
      this.app.assets.add(asset);
      asset.on("load", () => resolve(asset));
      asset.on("error", (err: string) =>
        reject(new Error(`Failed to load ${path}: ${err}`)),
      );
      this.app.assets.load(asset);
    });
  }
}
