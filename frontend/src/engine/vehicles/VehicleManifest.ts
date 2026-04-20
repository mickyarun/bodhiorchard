// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * VehicleManifest — Vehicle definitions for the garden engine.
 *
 * Each vehicle has a unique id, display name, GLB/glTF path, physics
 * dimensions, speed multiplier, and mount offset for the rider.
 *
 * Designed for easy extension — add bike/car entries here later.
 */

export interface VehicleDef {
  id: string
  name: string
  glb: string
  thumbnail: string
  /** Movement speed multiplier relative to walking speed. */
  speedMultiplier: number
  /**
   * Optional velocity thresholds (m/s) used by VehicleSystem to derive the
   * remote gait (Idle / Walk / Gallop) from observed position delta.
   * Values below `idleMax` → Idle; between → Walk; above `walkMax` → Gallop.
   * If unset, VehicleSystem derives defaults from `speedMultiplier`.
   */
  gaitThresholds?: { idleMax: number; walkMax: number }
  /** Rapier capsule radius when mounted. */
  physicsRadius: number
  /** Rapier capsule half-height when mounted. */
  physicsHalfHeight: number
  /** Local offset where the rider character is parented. */
  mountOffset: { x: number; y: number; z: number }
  /** Scale applied to the vehicle model. */
  scale: number
  /** Animation names for this vehicle. */
  animations: {
    idle: string
    walk: string
    gallop: string
  }
  /** Skill points cost to unlock. */
  unlockCost: number
}

const VEHICLES: VehicleDef[] = [
  {
    id: 'horse',
    name: 'Horse',
    glb: 'assets/vehicles/horse.gltf',
    thumbnail: 'assets/vehicles/thumbnails/horse.png',
    speedMultiplier: 2.0,
    physicsRadius: 0.5,
    physicsHalfHeight: 0.5,
    mountOffset: { x: 0, y: 0.55, z: 0 },
    scale: 0.22,
    animations: {
      idle: 'Idle',
      walk: 'Walk',
      gallop: 'Gallop',
    },
    unlockCost: 50,
  },
]

export function getVehicleDef(id: string): VehicleDef | undefined {
  return VEHICLES.find(v => v.id === id)
}

export function getAllVehicles(): readonly VehicleDef[] {
  return VEHICLES
}

export function getUnlockedVehicles(unlockedIds: Set<string>): VehicleDef[] {
  return VEHICLES.filter(v => unlockedIds.has(v.id))
}
