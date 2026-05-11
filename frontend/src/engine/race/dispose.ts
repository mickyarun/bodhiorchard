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
 * dispose — safe PlayCanvas resource-teardown helpers for the race module.
 *
 * PlayCanvas does NOT auto-free GPU VRAM on `entity.destroy()` — you must
 * explicitly destroy textures and materials. The engine also has a known
 * bug where calling `texture.destroy()` twice produces negative VRAM
 * counts in the profiler; see:
 *   https://forum.playcanvas.com/t/how-to-free-the-vram-of-destroyed-entities/1781
 *   https://github.com/playcanvas/engine/issues/4267
 *
 * These helpers wrap that cleanup with double-destroy guards, so callers
 * can dispose resources without worrying about invocation order or the
 * same resource being referenced from multiple owners.
 *
 * Usage convention for the race module:
 *   - Every file that creates a pc.Texture / pc.StandardMaterial / pc.Entity
 *     imports from here for its destroy() method.
 *   - Never call `.destroy()` directly on a pc.Texture in this module.
 *   - Materials must have their map references nulled out before destroy
 *     so the engine drops its GPU bindings — safeDestroyMaterial handles
 *     this automatically.
 */
import type * as pc from 'playcanvas'

/** Tracks already-destroyed textures to guard against the double-destroy bug. */
const _destroyedTextures = new WeakSet<pc.Texture>()
const _destroyedMaterials = new WeakSet<pc.StandardMaterial>()

/**
 * Destroy a pc.Texture safely.
 *
 * - null/undefined: no-op (convenient for optional fields).
 * - Already destroyed: no-op (prevents the negative-VRAM engine bug).
 * - Otherwise: calls texture.destroy() and marks it destroyed.
 */
export function safeDestroyTexture(tex: pc.Texture | null | undefined): void {
  if (!tex) return
  if (_destroyedTextures.has(tex)) return
  _destroyedTextures.add(tex)
  tex.destroy()
}

/**
 * Destroy a pc.StandardMaterial safely.
 *
 * Nulls out the common map references (diffuseMap, emissiveMap, normalMap,
 * opacityMap) before calling destroy so the engine drops GPU bindings. The
 * textures themselves are NOT destroyed here — the caller owns them and
 * should call safeDestroyTexture separately if they own the texture too.
 */
export function safeDestroyMaterial(mat: pc.StandardMaterial | null | undefined): void {
  if (!mat) return
  if (_destroyedMaterials.has(mat)) return
  _destroyedMaterials.add(mat)
  mat.diffuseMap = null
  mat.emissiveMap = null
  mat.normalMap = null
  mat.opacityMap = null
  mat.update()
  mat.destroy()
}

/**
 * Destroy a pc.Entity safely. `pc.Entity.destroy()` already cascades to
 * children, so this helper is thin — its value is the null-guard and the
 * single import point so grep is deterministic across the module.
 */
export function disposeEntity(entity: pc.Entity | null | undefined): void {
  if (!entity) return
  entity.destroy()
}
