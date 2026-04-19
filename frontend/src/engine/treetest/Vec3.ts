// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Vec3 — 3D vector/point class.
 * Direct port of Tree3D's Point3D.java.
 */

export class Vec3 {
  constructor(public x: number, public y: number, public z: number) {}

  add(other: Vec3): Vec3 {
    return new Vec3(this.x + other.x, this.y + other.y, this.z + other.z)
  }

  subtract(other: Vec3): Vec3 {
    return new Vec3(this.x - other.x, this.y - other.y, this.z - other.z)
  }

  length(): number {
    return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z)
  }

  /** Returns a new normalized Vec3 — pure, does not mutate. */
  normalized(): Vec3 {
    const len = this.length()
    if (len === 0) return new Vec3(0, 0, 0)
    return new Vec3(this.x / len, this.y / len, this.z / len)
  }

  /** Mutates this vector in place — use only when allocation must be avoided. */
  normalize(): void {
    const len = this.length()
    if (len > 0) { this.x /= len; this.y /= len; this.z /= len }
  }

  negate(): Vec3 {
    return new Vec3(-this.x, -this.y, -this.z)
  }

  static dot(a: Vec3, b: Vec3): number {
    return a.x * b.x + a.y * b.y + a.z * b.z
  }

  static cross(a: Vec3, b: Vec3): Vec3 {
    return new Vec3(
      a.y * b.z - a.z * b.y,
      a.z * b.x - a.x * b.z,
      a.x * b.y - a.y * b.x,
    )
  }

  static angleBetween(a: Vec3, b: Vec3): number {
    const lenA = a.length()
    const lenB = b.length()
    if (lenA === 0 || lenB === 0) return 0
    const cos = Vec3.dot(a, b) / (lenA * lenB)
    return Math.acos(Math.max(-1, Math.min(1, cos)))
  }

}
