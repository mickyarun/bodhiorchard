/**
 * LanternSystem — Glowing lantern posts along garden paths.
 *
 * Places a thin pole + emissive sphere at intervals along path routes.
 * No actual point lights — emissive material creates the glow illusion.
 *
 * Performance: ~20 posts + 20 spheres, shared materials, no shadows.
 */
import * as pc from 'playcanvas'

const LANTERN_SPACING = 6      // world units between lanterns along each path
const POLE_WIDTH = 0.06
const POLE_HEIGHT = 1.5
const LAMP_RADIUS = 0.12
const PATH_OFFSET = 0.8        // offset perpendicular to path direction (left side)

export class LanternSystem {
  private root: pc.Entity
  private poleMat: pc.StandardMaterial
  private lampMat: pc.StandardMaterial

  constructor(app: pc.AppBase) {
    this.root = new pc.Entity('LanternSystem')
    app.root.addChild(this.root)

    // Dark wood pole material
    this.poleMat = new pc.StandardMaterial()
    this.poleMat.diffuse = new pc.Color(0.3, 0.2, 0.12)
    this.poleMat.metalness = 0
    this.poleMat.gloss = 0.15
    this.poleMat.update()

    // Warm emissive lamp material — no point light, just glow
    this.lampMat = new pc.StandardMaterial()
    this.lampMat.diffuse = new pc.Color(1.0, 0.85, 0.4)
    this.lampMat.emissive = new pc.Color(1.0, 0.85, 0.4)
    this.lampMat.metalness = 0
    this.lampMat.gloss = 0.5
    this.lampMat.update()
  }

  /**
   * Place lanterns along path routes.
   * @param routes — array of {fromX, fromZ, toX, toZ} path segments
   */
  buildAlongRoutes(routes: Array<{ fromX: number; fromZ: number; toX: number; toZ: number }>): void {
    for (const route of routes) {
      const dx = route.toX - route.fromX
      const dz = route.toZ - route.fromZ
      const dist = Math.sqrt(dx * dx + dz * dz)
      if (dist < LANTERN_SPACING * 2) continue // skip very short paths

      const nx = dx / dist
      const nz = dz / dist
      // Perpendicular direction (left side of path)
      const px = -nz
      const pz = nx

      const count = Math.floor(dist / LANTERN_SPACING)
      for (let i = 1; i < count; i++) {
        const t = i / count
        const x = route.fromX + dx * t + px * PATH_OFFSET
        const z = route.fromZ + dz * t + pz * PATH_OFFSET

        this.createLantern(x, z)
      }
    }
  }

  destroy(): void {
    this.root.destroy()
    this.poleMat.destroy()
    this.lampMat.destroy()
  }

  private createLantern(x: number, z: number): void {
    // Pole
    const pole = new pc.Entity('LPole')
    pole.addComponent('render', { type: 'box' })
    pole.setLocalScale(POLE_WIDTH, POLE_HEIGHT, POLE_WIDTH)
    pole.setPosition(x, POLE_HEIGHT / 2, z)
    pole.render!.meshInstances[0].material = this.poleMat
    pole.render!.castShadows = false
    this.root.addChild(pole)

    // Lamp (sphere at top of pole)
    const lamp = new pc.Entity('LLamp')
    lamp.addComponent('render', { type: 'sphere' })
    const s = LAMP_RADIUS * 2
    lamp.setLocalScale(s, s, s)
    lamp.setPosition(x, POLE_HEIGHT + LAMP_RADIUS, z)
    lamp.render!.meshInstances[0].material = this.lampMat
    lamp.render!.castShadows = false
    this.root.addChild(lamp)
  }
}
