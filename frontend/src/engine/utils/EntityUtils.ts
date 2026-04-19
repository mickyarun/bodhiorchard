// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
