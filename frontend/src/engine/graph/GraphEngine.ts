// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * GraphEngine — standalone PlayCanvas engine for 3D force-directed graph.
 *
 * Architecture:
 * - Repos go through force simulation (repulsion + collision keeps them apart)
 * - Features are placed on a fixed Fibonacci sphere around their repo (no simulation)
 * - Features move with their repo as children
 *
 * This class is a thin orchestrator that wires together:
 *   GraphCameraController — orbit camera + smooth transitions
 *   GraphPickingSystem    — raycasting, hover, click
 *   ForceSimulator        — force-directed layout (pure math)
 *   GraphNodeBuilder      — PlayCanvas sphere entities
 *   GraphEdgeBuilder      — curved arc edges
 *   GraphLabelSystem      — billboard text labels
 *
 * Public API:
 *   init(container, w, h, callbacks?) — boots PlayCanvas
 *   setData(data)                     — builds graph from EngineData
 *   resize(w, h)                      — viewport resize
 *   focusOnNode(nodeId)               — focus camera on a node
 *   resetView()                       — reset to full graph view
 *   destroy()                         — cleanup
 */
import * as pc from "playcanvas";
import type { EngineData, EngineFeature } from "../types";
import { MaterialFactory } from "../rendering/MaterialFactory";
import { InputManager } from "../input/InputManager";
import {
  installContextLossHandlers,
  installVisibilityGate,
  installRenderErrorTrap,
} from "../utils/AppLifecycle";
import {
  ForceSimulator,
  type ForceNode,
  type ForceEdge,
} from "./ForceSimulator";
import { GraphNodeBuilder } from "./GraphNodeBuilder";
import { GraphEdgeBuilder, type EdgeHandle } from "./GraphEdgeBuilder";
import { GraphLabelSystem } from "./GraphLabelSystem";
import { GraphCameraController } from "./GraphCameraController";
import { GraphPickingSystem } from "./GraphPickingSystem";
import { GraphCrossRepoSystem } from "./GraphCrossRepoSystem";
import { GraphOverlaySystem } from "./GraphOverlaySystem";
import type { GraphCallbacks } from "./GraphTypes";

// ─── Layout Constants ───────────────────────────

/** Compute feature sphere radius based on count. Grows sub-linearly so clusters stay compact. */
function featureSphereRadius(count: number): number {
  if (count <= 1) return 3;
  if (count <= 5) return 3 + count * 0.5;
  return 5 + Math.sqrt(count) * 0.8;
}

const REPO_EDGE_LENGTH = 35;
const REPO_MASS = 10;
const WARMUP_ITERATIONS = 200;

// ─── Engine ─────────────────────────────────────

export class GraphEngine {
  private app: pc.AppBase | null = null;
  private root: pc.Entity | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private callbacks: GraphCallbacks = {};

  // Subsystems
  private input: InputManager | null = null;
  private materials: MaterialFactory | null = null;
  private camera: GraphCameraController | null = null;
  private picking: GraphPickingSystem | null = null;
  private simulator: ForceSimulator | null = null;
  private nodeBuilder: GraphNodeBuilder | null = null;
  private edgeBuilder: GraphEdgeBuilder | null = null;
  private labelSystem: GraphLabelSystem | null = null;
  private crossRepo: GraphCrossRepoSystem | null = null;
  private overlay: GraphOverlaySystem | null = null;

  // Cleanup hooks for context-loss + visibility lifecycle helpers wired
  // in init(). Drained in destroy() so a teardown does not leave dangling
  // canvas-level / document-level listeners pointing at the freed app.
  private lifecycleCleanups: Array<() => void> = [];

  // Entity tracking
  private nodeEntities = new Map<string, pc.Entity>();
  private edgeHandles = new Map<string, EdgeHandle>();
  private graphRoot: pc.Entity | null = null;

  // Feature positions: repo node ID → array of { featureId, offset Vec3 }
  private featureOffsets = new Map<
    string,
    { featureId: string; offset: pc.Vec3 }[]
  >();

  // IBL cubemap reference for cleanup
  private iblCubemap: pc.Texture | null = null;

  // Pre-allocated scratch vectors for simulation updates
  private readonly _tmpFrom = new pc.Vec3();
  private readonly _tmpTo = new pc.Vec3();

  // ─── Lifecycle ─────────────────────────────────

  async init(
    container: HTMLElement,
    width: number,
    height: number,
    callbacks?: GraphCallbacks,
  ): Promise<void> {
    this.callbacks = callbacks ?? {};

    this.canvas = document.createElement("canvas");
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvas.style.display = "block";
    container.appendChild(this.canvas);

    this.app = new pc.Application(this.canvas, {
      graphicsDeviceOptions: {
        antialias: true,
        alpha: false,
        preserveDrawingBuffer: false,
        // Discrete-GPU hint; silent fallback to integrated when none.
        powerPreference: 'high-performance',
      },
    });

    this.app.setCanvasFillMode(pc.FILLMODE_NONE);
    this.app.setCanvasResolution(pc.RESOLUTION_AUTO);
    this.app.graphicsDevice.maxPixelRatio = Math.min(
      window.devicePixelRatio,
      2,
    );
    this.app.resizeCanvas(width, height);

    this.lifecycleCleanups.push(
      installContextLossHandlers(this.canvas, this.app, 'GraphEngine'),
      installVisibilityGate(this.app),
      installRenderErrorTrap(this.app, 'GraphEngine'),
    );

    // PBR lighting
    this.app.scene.ambientLight = new pc.Color(0.35, 0.35, 0.4);
    (this.app.scene as unknown as Record<string, unknown>).exposure = 1.4;
    this.app.scene.skyboxIntensity = 0.4;
    this.setupIBL();

    // Root
    this.root = new pc.Entity("GraphRoot");
    this.app.root.addChild(this.root);

    // Lights
    this.createLights();

    // Subsystems
    this.camera = new GraphCameraController(this.root);
    this.input = new InputManager();
    this.input.init(this.canvas, this.app);
    this.materials = new MaterialFactory();
    this.nodeBuilder = new GraphNodeBuilder(this.materials);
    this.edgeBuilder = new GraphEdgeBuilder(this.materials);
    this.labelSystem = new GraphLabelSystem();
    this.labelSystem.setCameraEntity(this.camera.getEntity());
    this.picking = new GraphPickingSystem();
    this.picking.setTooltipEnricher((data, text) => {
      if (data.type === 'graph_feature' && this.crossRepo) {
        const count = this.crossRepo.getRepoCount(data.title);
        if (count > 1) {
          this.crossRepo.showLabelForTitle(data.title);
          return `${text}\n(${count} repos)`;
        }
      }
      // Hide label when hovering non-cross-repo nodes
      this.crossRepo?.showLabelForTitle(null);
      return text;
    });
    this.crossRepo = new GraphCrossRepoSystem(this.materials);
    this.crossRepo.setContext(this.app, this.camera.getEntity());
    this.overlay = new GraphOverlaySystem(this.materials);
    this.overlay.init();
    this.overlay.setCameraEntity(this.camera.getEntity());

    // Frame loop
    this.app.on("update", (dt: number) => this.onUpdate(dt));

    this.app.start();
    this.callbacks.onReady?.();
  }

  // ─── Data ──────────────────────────────────────

  async setData(data: EngineData): Promise<void> {
    if (!this.app || !this.root) return;

    this.clearGraph();
    this.graphRoot = new pc.Entity("GraphEntities");
    this.root.addChild(this.graphRoot);

    const { repos, features, relationships } = data;
    this.nodeBuilder!.assignRepoColors(repos.map((r) => r.repo_name));

    // ─── Force simulation: REPOS ONLY ─────────────
    const forceNodes: ForceNode[] = [];
    const forceEdges: ForceEdge[] = [];

    const repoCount = repos.length;
    for (let i = 0; i < repoCount; i++) {
      const repo = repos[i];
      let rx = 0, rz = 0;
      if (repoCount > 1) {
        const repoRadius = repoCount * 8;
        const angle = (2 * Math.PI * i) / repoCount;
        rx = Math.cos(angle) * repoRadius;
        rz = Math.sin(angle) * repoRadius;
      }
      forceNodes.push({
        id: `repo_${repo.repo_name}`,
        x: rx, y: 0, z: rz,
        vx: 0, vy: 0, vz: 0,
        mass: REPO_MASS,
        pinned: repoCount === 1,
        collides: true,
      });
    }

    // Repo-to-repo relationship edges
    const seenRelEdges = new Set<string>();
    for (const rel of relationships) {
      if (rel.source_repo === rel.target_repo) continue;
      const edgeKey = [rel.source_repo, rel.target_repo].sort().join("__");
      if (seenRelEdges.has(edgeKey)) continue;
      seenRelEdges.add(edgeKey);
      forceEdges.push({
        source: `repo_${rel.source_repo}`,
        target: `repo_${rel.target_repo}`,
        length: REPO_EDGE_LENGTH,
      });
    }

    this.simulator = new ForceSimulator(forceNodes, forceEdges);
    if (repoCount > 1) this.simulator.warmup(WARMUP_ITERATIONS);

    // ─── Create repo entities ─────────────────────
    for (const repo of repos) {
      const nodeId = `repo_${repo.repo_name}`;
      const entity = this.nodeBuilder!.buildRepoNode(repo);
      const fNode = this.simulator.getNode(nodeId);
      if (fNode) entity.setPosition(fNode.x, fNode.y, fNode.z);
      this.graphRoot.addChild(entity);
      this.nodeEntities.set(nodeId, entity);
      this.labelSystem!.createLabel(this.app!, repo.repo_name, entity, 2.2, 0.4);
    }

    // ─── Index features by repo ───────────────────
    const featuresByRepo = new Map<string, EngineFeature[]>();
    const unlinkedFeatures: EngineFeature[] = [];
    for (const f of features) {
      if (f.repo_name) {
        const arr = featuresByRepo.get(f.repo_name);
        if (arr) arr.push(f);
        else featuresByRepo.set(f.repo_name, [f]);
      } else {
        unlinkedFeatures.push(f);
      }
    }

    // ─── Create feature entities on Fibonacci sphere ─
    let featureIdx = 0;
    for (const repo of repos) {
      const repoFeatures = featuresByRepo.get(repo.repo_name) ?? [];
      const repoNodeId = `repo_${repo.repo_name}`;
      const repoEntity = this.nodeEntities.get(repoNodeId);
      if (!repoEntity) continue;

      const radius = featureSphereRadius(repoFeatures.length);
      const offsets: { featureId: string; offset: pc.Vec3 }[] = [];

      for (let j = 0; j < repoFeatures.length; j++) {
        const fId = `feat_${featureIdx}`;
        const n = repoFeatures.length;

        // Fibonacci sphere distribution
        const phi = Math.acos(1 - (2 * (j + 0.5)) / n);
        const theta = Math.PI * (1 + Math.sqrt(5)) * j;

        const offset = new pc.Vec3(
          radius * Math.sin(phi) * Math.cos(theta),
          radius * Math.cos(phi),
          radius * Math.sin(phi) * Math.sin(theta),
        );

        const entity = this.nodeBuilder!.buildFeatureNode(repoFeatures[j], featureIdx);
        const repoPos = repoEntity.getPosition();
        entity.setPosition(
          repoPos.x + offset.x,
          repoPos.y + offset.y,
          repoPos.z + offset.z,
        );
        this.graphRoot.addChild(entity);
        this.nodeEntities.set(fId, entity);
        offsets.push({ featureId: fId, offset });

        // Edge from repo to feature
        const from = repoEntity.getPosition().clone();
        const to = entity.getPosition().clone();
        const edgeColor = this.nodeBuilder!.getRepoColor(repo.repo_name);
        const handle = this.edgeBuilder!.buildEdge(from, to, `${repoNodeId}__${fId}`, edgeColor);
        this.graphRoot.addChild(handle.parent);
        this.edgeHandles.set(`${repoNodeId}__${fId}`, handle);

        featureIdx++;
      }

      this.featureOffsets.set(repoNodeId, offsets);
    }

    // ─── Unlinked features ────────────────────────
    if (unlinkedFeatures.length > 0) {
      const ulRadius = featureSphereRadius(unlinkedFeatures.length);
      for (let j = 0; j < unlinkedFeatures.length; j++) {
        const fId = `feat_${featureIdx}`;
        const n = unlinkedFeatures.length;
        const phi = Math.acos(1 - (2 * (j + 0.5)) / n);
        const theta = Math.PI * (1 + Math.sqrt(5)) * j;

        const entity = this.nodeBuilder!.buildFeatureNode(unlinkedFeatures[j], featureIdx);
        entity.setPosition(
          ulRadius * Math.sin(phi) * Math.cos(theta),
          ulRadius * Math.cos(phi),
          ulRadius * Math.sin(phi) * Math.sin(theta),
        );
        this.graphRoot.addChild(entity);
        this.nodeEntities.set(fId, entity);
        featureIdx++;
      }
    }

    // ─── Cross-repo feature arcs ────────────────────
    this.crossRepo?.build(this.nodeEntities, this.graphRoot);

    // ─── Developer skill overlays ─────────────────
    this.overlay?.setThreats(data.threats);
    this.overlay?.setBuds(data.buds);
    this.overlay?.build(data.feature_skills, this.nodeEntities, this.graphRoot);
    this.overlay?.buildBudBadges(this.app!, this.nodeEntities, this.graphRoot);

    // ─── Auto-frame camera to fit graph ───────────
    this.autoFrameCamera(repos, featuresByRepo);
  }

  // ─── Public API ────────────────────────────────

  focusOnNode(nodeId: string): void {
    const entity = this.nodeEntities.get(nodeId);
    if (!entity || !this.camera) return;

    const pos = entity.getPosition();
    const offsets = this.featureOffsets.get(nodeId);
    const featureCount = offsets?.length ?? 0;
    const idealDist = featureSphereRadius(featureCount) * 3.5;

    this.camera.focusOn(pos.x, pos.y, pos.z, idealDist, 20);
  }

  resetView(): void {
    this.camera?.resetView();
  }

  /** Toggle cross-repo feature arcs on/off. */
  setCrossRepoLinksVisible(visible: boolean): void {
    this.crossRepo?.setVisible(visible);
  }

  /** Get the number of repos a feature spans (1 = single-repo). */
  getFeatureRepoCount(title: string): number {
    return this.crossRepo?.getRepoCount(title) ?? 1;
  }

  /** Toggle bus factor warning rings on features. */
  setBusFactorVisible(visible: boolean): void {
    this.overlay?.setBusFactorVisible(visible);
  }

  /** Highlight all features a developer is skilled in, dim others. */
  highlightDeveloper(userId: string): void {
    if (!this.graphRoot) return;
    this.overlay?.highlightDeveloper(userId, this.nodeEntities, this.graphRoot);
  }

  /** Clear developer highlight and restore all opacities. */
  clearHighlight(): void {
    this.overlay?.clearHighlight();
  }

  /** Toggle status color overlay (features recolored by planned/in_progress/implemented). */
  setStatusOverlay(active: boolean): void {
    this.overlay?.setStatusOverlay(active, this.nodeEntities);
  }

  /** Toggle threat/bug highlight overlay. */
  setThreatOverlay(active: boolean): void {
    if (!this.graphRoot) return;
    this.overlay?.setThreatOverlay(active, this.nodeEntities, this.graphRoot);
  }

  /** Toggle BUD lifecycle badges on features. */
  setBudBadgesVisible(visible: boolean): void {
    this.overlay?.setBudBadgesVisible(visible);
  }

  /** Filter graph to show only the selected repo and its features. null = show all. */
  filterByRepo(repoName: string | null): void {
    if (!repoName) {
      this.overlay?.clearHighlight();
      this.resetView();
      return;
    }
    // Find the repo entity and all its features
    const activeIds = new Set<string>();
    const repoNodeId = `repo_${repoName}`;
    if (this.nodeEntities.has(repoNodeId)) {
      activeIds.add(repoNodeId);
    }
    // Features that belong to this repo
    const offsets = this.featureOffsets.get(repoNodeId);
    if (offsets) {
      for (const { featureId } of offsets) activeIds.add(featureId);
    }
    // Dim unrelated nodes
    if (this.overlay && this.graphRoot) {
      this.overlay.dimOnly(activeIds, this.nodeEntities);
    }
    // Focus camera on the selected repo
    this.focusOnNode(repoNodeId);
  }

  /** Filter graph to show only features associated with a developer. null = show all. */
  filterByDeveloper(userId: string | null): void {
    if (!userId) {
      this.overlay?.clearHighlight();
      return;
    }
    if (!this.graphRoot) return;
    this.overlay?.highlightDeveloper(userId, this.nodeEntities, this.graphRoot);
  }

  resize(width: number, height: number): void {
    this.app?.resizeCanvas(width, height);
  }

  destroy(): void {
    // Same defensive pattern as GardenEngine.destroy: per-subsystem try/catch
    // so one throw doesn't cascade and skip past `this.app.destroy()`. Without
    // this, a failed subsystem teardown can strand the entire pc.AppBase +
    // scene graph in the heap (~36 MB per leaked instance).
    const safe = (label: string, fn: () => void): void => {
      try { fn() } catch (err) {
        console.warn(`[GraphEngine.destroy] ${label} threw:`, err)
      }
    }

    try {
      safe('clearGraph',       () => this.clearGraph())
      this.simulator = null
      safe('crossRepo.destroy', () => this.crossRepo?.destroy())
      this.crossRepo = null
      safe('overlay.destroy',   () => this.overlay?.destroy())
      this.overlay = null
      safe('input.destroy',     () => this.input?.destroy())
      this.input = null
      this.picking = null
      this.camera = null
      safe('iblCubemap.destroy', () => this.iblCubemap?.destroy())
      this.iblCubemap = null
      safe('materials.clear',    () => this.materials?.clear())
      this.materials = null
      for (const cleanup of this.lifecycleCleanups) {
        safe('lifecycleCleanup', cleanup)
      }
      this.lifecycleCleanups = []
    } finally {
      // ALWAYS run — releasing pc.AppBase is the most important step.
      if (this.app) {
        safe('app.destroy', () => this.app!.destroy())
        this.app = null
      }
      if (this.canvas) {
        safe('canvas.remove', () => this.canvas?.remove())
        this.canvas = null
      }
    }
  }

  // ─── Frame Loop ────────────────────────────────

  private onUpdate(dt: number): void {
    // Camera
    this.camera?.update(dt, this.input);

    // Force simulation (repos only — features are fixed offsets)
    this.updateSimulation(dt);

    // Billboard labels + badge billboarding + cross-repo label billboarding
    this.labelSystem?.updateBillboards();
    this.overlay?.updatePositions(this.nodeEntities);
    this.crossRepo?.updatePositions(this.nodeEntities);

    // Picking
    if (this.camera && this.input && this.picking) {
      this.picking.update(
        this.camera.getEntity(),
        this.input,
        this.nodeEntities,
        this.callbacks,
      );
    }
  }

  // ─── Simulation ────────────────────────────────

  private updateSimulation(dt: number): void {
    if (!this.simulator || this.simulator.isSettled()) return;

    this.simulator.step(dt);

    // Update repo positions
    for (const fNode of this.simulator.nodes) {
      const entity = this.nodeEntities.get(fNode.id);
      if (entity) entity.setPosition(fNode.x, fNode.y, fNode.z);
    }

    // Move features with their repo + update edges
    for (const [repoId, offsets] of this.featureOffsets) {
      const repoEntity = this.nodeEntities.get(repoId);
      if (!repoEntity) continue;
      const repoPos = repoEntity.getPosition();

      for (const { featureId, offset } of offsets) {
        const featEntity = this.nodeEntities.get(featureId);
        if (featEntity) {
          featEntity.setPosition(
            repoPos.x + offset.x,
            repoPos.y + offset.y,
            repoPos.z + offset.z,
          );
        }

        const edgeId = `${repoId}__${featureId}`;
        const handle = this.edgeHandles.get(edgeId);
        if (handle) {
          this._tmpFrom.set(repoPos.x, repoPos.y, repoPos.z);
          this._tmpTo.set(
            repoPos.x + offset.x,
            repoPos.y + offset.y,
            repoPos.z + offset.z,
          );
          this.edgeBuilder!.updateEdge(handle, this._tmpFrom, this._tmpTo);
        }
      }
    }

    // Update cross-repo arcs (features moved, so arc endpoints changed)
    this.crossRepo?.updatePositions(this.nodeEntities);

    // Update bus factor ring positions
    this.overlay?.updatePositions(this.nodeEntities);
  }

  // ─── Setup Helpers ─────────────────────────────

  private createLights(): void {
    if (!this.root) return;

    const sun = new pc.Entity("GraphSun");
    sun.addComponent("light", {
      type: "directional",
      color: new pc.Color(1, 0.97, 0.92),
      intensity: 1.8,
      castShadows: false,
    });
    sun.setEulerAngles(55, -30, 0);
    this.root.addChild(sun);

    const fill = new pc.Entity("GraphFill");
    fill.addComponent("light", {
      type: "directional",
      color: new pc.Color(0.5, 0.6, 0.9),
      intensity: 0.6,
      castShadows: false,
    });
    fill.setEulerAngles(-50, 40, 0);
    this.root.addChild(fill);
  }

  private setupIBL(): void {
    if (!this.app) return;
    const size = 64;
    const device = this.app.graphicsDevice;
    const faces: Uint8Array[] = [];
    for (let face = 0; face < 6; face++) {
      const data = new Uint8Array(size * size * 4);
      for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
          const idx = (y * size + x) * 4;
          const t = y / size;
          data[idx] = Math.round(20 + t * 15);
          data[idx + 1] = Math.round(22 + t * 18);
          data[idx + 2] = Math.round(30 + t * 25);
          data[idx + 3] = 255;
        }
      }
      faces.push(data);
    }
    const cubemap = new pc.Texture(device, {
      width: size,
      height: size,
      format: pc.PIXELFORMAT_RGBA8,
      cubemap: true,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      levels: [faces],
    });
    this.app.scene.skybox = cubemap;
    this.iblCubemap = cubemap;
  }

  private autoFrameCamera(
    repos: EngineData["repos"],
    featuresByRepo: Map<string, EngineFeature[]>,
  ): void {
    if (!this.camera) return;

    let maxExtent = 10;
    for (const [, entity] of this.nodeEntities) {
      const pos = entity.getPosition();
      const d = Math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z);
      maxExtent = Math.max(maxExtent, d);
    }

    let maxFeatureRadius = 0;
    for (const repo of repos) {
      const rf = featuresByRepo.get(repo.repo_name) ?? [];
      maxFeatureRadius = Math.max(maxFeatureRadius, featureSphereRadius(rf.length));
    }

    const totalExtent = maxExtent + maxFeatureRadius;
    const distance = (totalExtent * 0.9) / Math.tan(this.camera.halfFovRad);
    this.camera.setFullView(distance, 10);
  }

  private clearGraph(): void {
    if (this.graphRoot) {
      this.graphRoot.destroy();
      this.graphRoot = null;
    }
    this.nodeEntities.clear();
    this.edgeHandles.clear();
    this.featureOffsets.clear();
    this.labelSystem?.destroy();
    this.nodeBuilder?.destroy();
    this.edgeBuilder?.destroy();
    this.crossRepo?.destroy();
    this.overlay?.destroy();

    if (this.materials) {
      this.nodeBuilder = new GraphNodeBuilder(this.materials);
      this.edgeBuilder = new GraphEdgeBuilder(this.materials);
      this.crossRepo = new GraphCrossRepoSystem(this.materials);
      if (this.app && this.camera) {
        this.crossRepo.setContext(this.app, this.camera.getEntity());
      }
      this.overlay = new GraphOverlaySystem(this.materials);
      this.overlay.init();
      if (this.camera) this.overlay.setCameraEntity(this.camera.getEntity());
    }
    this.labelSystem = new GraphLabelSystem();
    if (this.camera) this.labelSystem.setCameraEntity(this.camera.getEntity());
  }
}
