/**
 * Mat3 — 3×3 rotation matrix.
 * Direct port of Tree3D's RotationMatrix.java.
 * Uses Rodrigues' rotation formula for arbitrary axis rotation.
 */
import { Vec3 } from './Vec3'

export class Mat3 {
  /** Row-major 3×3 matrix: [r0c0, r0c1, r0c2, r1c0, ...] */
  readonly m: number[]

  constructor(m?: number[]) {
    this.m = m ?? [1, 0, 0, 0, 1, 0, 0, 0, 1] // identity
  }

  multiply(other: Mat3): Mat3 {
    const a = this.m, b = other.m
    return new Mat3([
      a[0]*b[0] + a[1]*b[3] + a[2]*b[6],  a[0]*b[1] + a[1]*b[4] + a[2]*b[7],  a[0]*b[2] + a[1]*b[5] + a[2]*b[8],
      a[3]*b[0] + a[4]*b[3] + a[5]*b[6],  a[3]*b[1] + a[4]*b[4] + a[5]*b[7],  a[3]*b[2] + a[4]*b[5] + a[5]*b[8],
      a[6]*b[0] + a[7]*b[3] + a[8]*b[6],  a[6]*b[1] + a[7]*b[4] + a[8]*b[7],  a[6]*b[2] + a[7]*b[5] + a[8]*b[8],
    ])
  }

  multiplyVec3(v: Vec3): Vec3 {
    const a = this.m
    return new Vec3(
      a[0]*v.x + a[1]*v.y + a[2]*v.z,
      a[3]*v.x + a[4]*v.y + a[5]*v.z,
      a[6]*v.x + a[7]*v.y + a[8]*v.z,
    )
  }

  static identity(): Mat3 { return new Mat3() }

  static rotateX(theta: number): Mat3 {
    const c = Math.cos(theta), s = Math.sin(theta)
    return new Mat3([1, 0, 0, 0, c, -s, 0, s, c])
  }

  static rotateY(theta: number): Mat3 {
    const c = Math.cos(theta), s = Math.sin(theta)
    return new Mat3([c, 0, s, 0, 1, 0, -s, 0, c])
  }

  /** Rodrigues' rotation formula — rotate around arbitrary axis. Does not mutate input. */
  static rotateAxis(axis: Vec3, theta: number): Mat3 {
    const len = axis.length()
    if (len === 0) return Mat3.identity()
    const s = Math.sin(theta), c = Math.cos(theta)
    const x = axis.x / len, y = axis.y / len, z = axis.z / len
    return new Mat3([
      c + (1-c)*x*x,     (1-c)*x*y - s*z,   (1-c)*x*z + s*y,
      (1-c)*x*y + s*z,   c + (1-c)*y*y,      (1-c)*y*z - s*x,
      (1-c)*x*z - s*y,   (1-c)*y*z + s*x,    c + (1-c)*z*z,
    ])
  }

  /** Rotate 'start' direction toward 'destination' by 'amount' fraction of the angle between them. */
  static rotateToward(start: Vec3, destination: Vec3, amount: number): Mat3 {
    let perp = Vec3.cross(start, destination)
    const angle = Vec3.angleBetween(start, destination)
    if (angle === 0) return Mat3.identity()
    if (angle >= Math.PI) perp = new Vec3(0, 0, 1)
    return Mat3.rotateAxis(perp, amount * angle)
  }
}
