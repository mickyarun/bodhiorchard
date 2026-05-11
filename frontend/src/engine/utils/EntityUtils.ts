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
 * Entity cleanup utilities for PlayCanvas.
 */
import * as pc from 'playcanvas'

/**
 * Recursively destroy an entity and all its children,
 * removing from parent and freeing GPU resources.
 */
export function destroyEntity(entity: pc.Entity): void {
  entity.destroy()
}

/**
 * Remove all children from an entity and destroy them.
 */
export function clearChildren(entity: pc.Entity): void {
  while (entity.children.length > 0) {
    const child = entity.children[0] as pc.Entity
    child.destroy()
  }
}

/**
 * Destroy a material and its textures.
 */
export function disposeMaterial(material: pc.Material): void {
  if (material instanceof pc.StandardMaterial) {
    const texProps = [
      'diffuseMap', 'normalMap', 'heightMap', 'emissiveMap',
      'glossMap', 'metalnessMap', 'aoMap', 'opacityMap',
    ] as const
    for (const prop of texProps) {
      const tex = (material as unknown as Record<string, pc.Texture | null>)[prop]
      if (tex) tex.destroy()
    }
  }
  material.destroy()
}
