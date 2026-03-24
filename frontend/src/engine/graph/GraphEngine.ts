/**
 * GraphEngine — standalone PlayCanvas engine for 3D force-directed graph.
 *
 * Architecture:
 * - Repos go through force simulation (repulsion + collision keeps them apart)
 * - Features are placed on a fixed Fibonacci sphere around their repo (no simulation)
 * - Features move with their repo as children
 *
 * Public API:
 *   init(container, w, h, callbacks?) — boots PlayCanvas
 *   setData(data)                     — builds graph from EngineData
 *   resize(w, h)                      — viewport resize
 *   focusOnNode(nodeId)               — focus camera on a node
 *   destroy()                         — cleanup
 */
import * as pc from "playcanvas";
import type { EngineData, EngineFeature } from "../types";
import { MaterialFactory } from "../rendering/MaterialFactory";
import { InputManager } from "../input/InputManager";
import {
  ForceSimulator,
  type ForceNode,
  type ForceEdge,
} from "./ForceSimulator";
import { GraphNodeBuilder } from "./GraphNodeBuilder";
import { GraphEdgeBuilder, type EdgeHandle } from "./GraphEdgeBuilder";
import { GraphLabelSystem } from "./GraphLabelSystem";

// ─── Callback Types ─────────────────────────────

export interface GraphRepoInfo {
  repoName: string;
  health: string;
  growthStage: string;
  totalFiles: number;
  totalCommits: number;
}

export interface GraphFeatureInfo {
  title: string;
  status: string;
  repoName: string | null;
  sourceRef: string | null;
  fromBud: number | null;
  branchName: string | null;
}

export interface GraphCallbacks {
  onRepoClick?: (info: GraphRepoInfo) => void;
  onFeatureClick?: (info: GraphFeatureInfo) => void;
  onHover?: (
    tooltip: { text: string; screenX: number; screenY: number } | null,
  ) => void;
  onReady?: () => void;
}

// ─── Layout Constants ───────────────────────────

/**
 * Compute feature sphere radius based on count.
 * Grows sub-linearly so clusters stay compact.
 */
function featureSphereRadius(count: number): number {
  if (count <= 1) return 3;
  if (count <= 5) return 3 + count * 0.5;
  return 5 + Math.sqrt(count) * 0.8; // ~7 for 10, ~9 for 20, ~11 for 50
}

const REPO_EDGE_LENGTH = 35;
const REPO_MASS = 10;
const WARMUP_ITERATIONS = 200;

// ─── Engine ─────────────────────────────────────

export class GraphEngine {
  private app: pc.AppBase | null = null;
  private root: pc.Entity | null = null;
  private camera: pc.Entity | null = null;
  private input: InputManager | null = null;
  private materials: MaterialFactory | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private callbacks: GraphCallbacks = {};

  // Simple orbit camera — start facing front, slightly above
  private camYaw = 0;
  private camPitch = 30;
  private camDistance = 60;
  private camTarget = new pc.Vec3(0, 0, 0);

  // Graph subsystems
  private simulator: ForceSimulator | null = null;
  private nodeBuilder: GraphNodeBuilder | null = null;
  private edgeBuilder: GraphEdgeBuilder | null = null;
  private labelSystem: GraphLabelSystem | null = null;

  // Entity tracking
  private nodeEntities = new Map<string, pc.Entity>();
  private edgeHandles = new Map<string, EdgeHandle>();
  private graphRoot: pc.Entity | null = null;

  // Feature positions: repo node ID → array of { featureId, offset Vec3 }
  private featureOffsets = new Map<
    string,
    { featureId: string; offset: pc.Vec3 }[]
  >();

  // Hover state
  private lastHoveredId: string | null = null;
  private lastHoverPos = { x: -1, y: -1 };

  // Rotation animation
  private rotationSpeed = 5;

  // IBL cubemap reference for cleanup
  private iblCubemap: pc.Texture | null = null;

  // Pre-allocated scratch vectors
  private readonly _tmpFrom = new pc.Vec3();
  private readonly _tmpTo = new pc.Vec3();
  private readonly _rayFrom = new pc.Vec3();
  private readonly _rayTo = new pc.Vec3();
  private readonly _rayDir = new pc.Vec3();

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
      },
    });

    this.app.setCanvasFillMode(pc.FILLMODE_NONE);
    this.app.setCanvasResolution(pc.RESOLUTION_AUTO);
    this.app.graphicsDevice.maxPixelRatio = Math.min(
      window.devicePixelRatio,
      2,
    );
    this.app.resizeCanvas(width, height);

    // PBR lighting
    this.app.scene.ambientLight = new pc.Color(0.35, 0.35, 0.4);
    const scene = this.app.scene as unknown as Record<string, unknown>;
    scene.toneMapping = pc.TONEMAP_ACES;
    scene.gammaCorrection = pc.GAMMA_SRGB;
    scene.exposure = 1.4;
    this.app.scene.skyboxIntensity = 0.4;
    this.setupIBL();

    // Root
    this.root = new pc.Entity("GraphRoot");
    this.app.root.addChild(this.root);

    // Camera
    this.camera = new pc.Entity("GraphCamera");
    this.camera.addComponent("camera", {
      clearColor: new pc.Color(0.06, 0.07, 0.1),
      projection: pc.PROJECTION_PERSPECTIVE,
      fov: 45,
      nearClip: 0.1,
      farClip: 1000,
      frustumCulling: true,
    });
    this.root.addChild(this.camera);
    this.updateCameraOrbit();

    // Lights
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

    // Input
    this.input = new InputManager();
    this.input.init(this.canvas);

    // Materials + subsystems
    this.materials = new MaterialFactory();
    this.nodeBuilder = new GraphNodeBuilder(this.materials);
    this.edgeBuilder = new GraphEdgeBuilder(this.materials);
    this.labelSystem = new GraphLabelSystem();
    this.labelSystem.setCameraEntity(this.camera);

    // Frame loop
    this.app.on("update", (dt: number) => this.onUpdate(dt));

    this.app.start();
    this.callbacks.onReady?.();
  }

  /** Build graph from engine data. */
  async setData(data: EngineData): Promise<void> {
    if (!this.app || !this.root) return;

    this.clearGraph();
    this.graphRoot = new pc.Entity("GraphEntities");
    this.root.addChild(this.graphRoot);

    const repos = data.repos;
    const features = data.features;
    const relationships = data.relationships;

    this.nodeBuilder!.assignRepoColors(repos.map((r) => r.repo_name));

    // ─── Force simulation: REPOS ONLY ─────────────
    const forceNodes: ForceNode[] = [];
    const forceEdges: ForceEdge[] = [];

    const repoCount = repos.length;
    for (let i = 0; i < repoCount; i++) {
      const repo = repos[i];
      // Single repo → place at origin. Multiple → arrange in circle.
      let rx = 0,
        rz = 0;
      if (repoCount > 1) {
        const repoRadius = repoCount * 8;
        const angle = (2 * Math.PI * i) / repoCount;
        rx = Math.cos(angle) * repoRadius;
        rz = Math.sin(angle) * repoRadius;
      }
      forceNodes.push({
        id: `repo_${repo.repo_name}`,
        x: rx,
        y: 0,
        z: rz,
        vx: 0,
        vy: 0,
        vz: 0,
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
      this.labelSystem!.createLabel(
        this.app!,
        repo.repo_name,
        entity,
        2.2,
        0.4,
      );
    }

    // ─── Index features by repo ───────────────────
    const featuresByRepo = new Map<string, EngineFeature[]>();
    for (const f of features) {
      const key = f.repo_name ?? "";
      const arr = featuresByRepo.get(key);
      if (arr) arr.push(f);
      else featuresByRepo.set(key, [f]);
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

        const entity = this.nodeBuilder!.buildFeatureNode(
          repoFeatures[j],
          featureIdx,
        );
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
        const handle = this.edgeBuilder!.buildEdge(
          from,
          to,
          `${repoNodeId}__${fId}`,
          edgeColor,
        );
        this.graphRoot.addChild(handle.parent);
        this.edgeHandles.set(`${repoNodeId}__${fId}`, handle);

        featureIdx++;
      }

      this.featureOffsets.set(repoNodeId, offsets);
    }

    // Compute the bounding extent of the entire graph
    let maxExtent = 10;
    for (const [, entity] of this.nodeEntities) {
      const pos = entity.getPosition();
      const d = Math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z);
      maxExtent = Math.max(maxExtent, d);
    }
    // Add the largest feature sphere radius for padding
    let maxFeatureRadius = 0;
    for (const repo of repos) {
      const rf = featuresByRepo.get(repo.repo_name) ?? [];
      maxFeatureRadius = Math.max(
        maxFeatureRadius,
        featureSphereRadius(rf.length),
      );
    }
    const totalExtent = maxExtent + maxFeatureRadius;

    // Camera distance to fit: extent / tan(halfFov), with padding
    const halfFovRad = ((45 / 2) * Math.PI) / 180;
    this.camDistance = (totalExtent * 0.9) / Math.tan(halfFovRad);
    this.camTarget.set(0, 0, 0);
    // Low pitch (nearly level) for the panoramic horizontal view
    this.camPitch = 10;
    this.camYaw = 0;
    this.updateCameraOrbit();
  }

  // ─── Camera ─────────────────────────────────────

  private updateCameraOrbit(): void {
    if (!this.camera) return;
    const pitchRad = (this.camPitch * Math.PI) / 180;
    const yawRad = (this.camYaw * Math.PI) / 180;
    const x =
      this.camTarget.x +
      this.camDistance * Math.cos(pitchRad) * Math.sin(yawRad);
    const y = this.camTarget.y + this.camDistance * Math.sin(pitchRad);
    const z =
      this.camTarget.z +
      this.camDistance * Math.cos(pitchRad) * Math.cos(yawRad);
    this.camera.setPosition(x, y, z);
    this.camera.lookAt(this.camTarget);
  }

  // ─── Frame Loop ─────────────────────────────────

  private onUpdate(dt: number): void {
    let cameraChanged = false;

    // Auto-rotation: rotate camera yaw (not graphRoot — avoids coordinate mismatch for picking)
    if (this.rotationSpeed > 0) {
      this.camYaw += this.rotationSpeed * dt;
      cameraChanged = true;
    }

    // Camera controls: drag orbit, scroll zoom
    if (this.input) {
      const orbit = this.input.getOrbitDelta();
      if (orbit.dx !== 0 || orbit.dy !== 0) {
        this.camYaw -= orbit.dx * 0.3;
        this.camPitch = Math.max(
          5,
          Math.min(85, this.camPitch + orbit.dy * 0.3),
        );
        cameraChanged = true;
      }

      const scroll = this.input.getScrollDelta();
      if (scroll !== 0) {
        this.camDistance = Math.max(
          10,
          Math.min(300, this.camDistance - scroll * 3),
        );
        cameraChanged = true;
      }
      // Consume pan delta (panning not supported in graph view)
      this.input.getPanDelta();
    }

    if (cameraChanged) this.updateCameraOrbit();

    // Force simulation (repos only — features are fixed offsets)
    if (this.simulator && !this.simulator.isSettled()) {
      this.simulator.step(dt);

      // Update repo positions
      for (const fNode of this.simulator.nodes) {
        const entity = this.nodeEntities.get(fNode.id);
        if (entity) entity.setPosition(fNode.x, fNode.y, fNode.z);
      }

      // Move features with their repo
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

          // Update edge
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
    }

    // Billboard labels
    this.labelSystem?.updateBillboards();

    // Picking
    this.handlePicking();
  }

  // ─── Raycasting / Picking ─────────────────────

  private handlePicking(): void {
    if (!this.app || !this.camera || !this.input) return;

    const click = this.input.consumeClick();
    const hoverPos = this.input.getHoverPos();

    if (click) {
      const hit = this.raycast(click.x, click.y);
      if (hit) {
        const userData = (hit as unknown as Record<string, unknown>)
          ._userData as Record<string, unknown> | undefined;
        if (userData?.type === "graph_repo") {
          this.callbacks.onRepoClick?.({
            repoName: userData.repoName as string,
            health: userData.health as string,
            growthStage: userData.growthStage as string,
            totalFiles: userData.totalFiles as number,
            totalCommits: userData.totalCommits as number,
          });
        } else if (userData?.type === "graph_feature") {
          this.callbacks.onFeatureClick?.({
            title: userData.title as string,
            status: userData.status as string,
            repoName: userData.repoName as string | null,
            sourceRef: userData.sourceRef as string | null,
            fromBud: userData.fromBud as number | null,
            branchName: userData.branchName as string | null,
          });
        }
      }
    }

    // Hover — skip if mouse hasn't moved
    if (
      hoverPos.x === this.lastHoverPos.x &&
      hoverPos.y === this.lastHoverPos.y
    )
      return;
    this.lastHoverPos.x = hoverPos.x;
    this.lastHoverPos.y = hoverPos.y;

    const hit = this.raycast(hoverPos.x, hoverPos.y);
    if (hit) {
      const userData = (hit as unknown as Record<string, unknown>)._userData as
        | Record<string, unknown>
        | undefined;
      const nodeId =
        (userData?.repoName as string) ?? (userData?.title as string) ?? "";
      if (nodeId !== this.lastHoveredId) {
        this.lastHoveredId = nodeId;
        let text = "";
        if (userData?.type === "graph_repo")
          text = `${userData.repoName} (${userData.health})`;
        else if (userData?.type === "graph_feature")
          text = `${userData.title}\n[${userData.status}]`;
        if (text)
          this.callbacks.onHover?.({
            text,
            screenX: hoverPos.x,
            screenY: hoverPos.y,
          });
      }
    } else if (this.lastHoveredId) {
      this.lastHoveredId = null;
      this.callbacks.onHover?.(null);
    }
  }

  private raycast(screenX: number, screenY: number): pc.Entity | null {
    if (!this.camera?.camera || !this.app) return null;

    const cam = this.camera.camera;
    cam.screenToWorld(screenX, screenY, cam.nearClip, this._rayFrom);
    cam.screenToWorld(screenX, screenY, cam.farClip, this._rayTo);
    this._rayDir.sub2(this._rayTo, this._rayFrom).normalize();

    let closestEntity: pc.Entity | null = null;
    let closestDist = Infinity;

    for (const [, entity] of this.nodeEntities) {
      if (!entity.tags.has("pickable")) continue;
      const pos = entity.getPosition();
      const scale = entity.getLocalScale();
      const radius = Math.max(scale.x, scale.y, scale.z) / 2;
      const dist = this.raySphereIntersect(
        this._rayFrom,
        this._rayDir,
        pos,
        radius,
      );
      if (dist !== null && dist < closestDist) {
        closestDist = dist;
        closestEntity = entity;
      }
    }

    return closestEntity;
  }

  private raySphereIntersect(
    origin: pc.Vec3,
    dir: pc.Vec3,
    center: pc.Vec3,
    radius: number,
  ): number | null {
    const ox = origin.x - center.x;
    const oy = origin.y - center.y;
    const oz = origin.z - center.z;
    const a = dir.x * dir.x + dir.y * dir.y + dir.z * dir.z;
    const b = 2 * (ox * dir.x + oy * dir.y + oz * dir.z);
    const c = ox * ox + oy * oy + oz * oz - radius * radius;
    const discriminant = b * b - 4 * a * c;
    if (discriminant < 0) return null;
    const t = (-b - Math.sqrt(discriminant)) / (2 * a);
    return t > 0 ? t : null;
  }

  // ─── IBL ─────────────────────────────────────────

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

  // ─── Public API ───────────────────────────────

  focusOnNode(nodeId: string): void {
    const entity = this.nodeEntities.get(nodeId);
    if (entity) {
      this.camTarget.copy(entity.getPosition());
      this.camDistance = 30;
      this.updateCameraOrbit();
    }
  }

  resize(width: number, height: number): void {
    this.app?.resizeCanvas(width, height);
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

    if (this.materials) {
      this.nodeBuilder = new GraphNodeBuilder(this.materials);
      this.edgeBuilder = new GraphEdgeBuilder(this.materials);
    }
    this.labelSystem = new GraphLabelSystem();
    if (this.camera) this.labelSystem.setCameraEntity(this.camera);
  }

  destroy(): void {
    this.clearGraph();
    this.simulator = null;
    this.input?.destroy();
    this.input = null;
    this.iblCubemap?.destroy();
    this.iblCubemap = null;
    this.materials?.clear();
    this.materials = null;
    if (this.app) {
      this.app.destroy();
      this.app = null;
    }
    if (this.canvas) {
      this.canvas.remove();
      this.canvas = null;
    }
  }
}
