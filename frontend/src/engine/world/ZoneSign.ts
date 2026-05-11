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
 * ZoneSign — Canvas-textured wooden sign that labels a zone.
 *
 * Creates a simple sign post: brown pole + flat board with text painted
 * via Canvas2D texture. Each sign faces the orchard center so it's
 * readable when approaching from the middle of the garden.
 */
import * as pc from 'playcanvas'

const SIGN_WIDTH = 1.6
const SIGN_HEIGHT = 0.5
const POLE_HEIGHT = 1.4
const POLE_THICKNESS = 0.08
const TEX_W = 256
const TEX_H = 80

/** Display names for each zone. */
const ZONE_LABELS: Record<string, string> = {
  coffee_bar: 'Coffee Bar',
  cafeteria: 'Cafeteria',
  housing: 'Village',
  pool: 'Pool',
  pavilion: 'Standup',
  orchard: 'Orchard',
}

export class ZoneSign {
  /**
   * Create a sign entity at the given position, facing toward (0,0).
   */
  static create(
    app: pc.AppBase,
    zoneName: string,
    x: number,
    z: number,
  ): pc.Entity {
    const label = ZONE_LABELS[zoneName] ?? zoneName
    const root = new pc.Entity(`Sign_${zoneName}`)
    root.setPosition(x, 0, z)

    // Face toward world center (orchard)
    const angle = Math.atan2(-x, -z) * (180 / Math.PI)
    root.setLocalEulerAngles(0, angle, 0)

    // Pole
    const pole = new pc.Entity('Pole')
    pole.addComponent('render', { type: 'box' })
    pole.setLocalScale(POLE_THICKNESS, POLE_HEIGHT, POLE_THICKNESS)
    pole.setLocalPosition(0, POLE_HEIGHT / 2, 0)

    const poleMat = new pc.StandardMaterial()
    poleMat.diffuse = new pc.Color(0.45, 0.30, 0.15) // brown
    poleMat.metalness = 0
    poleMat.gloss = 0.1
    poleMat.update()
    pole.render!.meshInstances[0].material = poleMat
    root.addChild(pole)

    // Board
    const board = new pc.Entity('Board')
    board.addComponent('render', { type: 'plane' })
    board.setLocalScale(SIGN_WIDTH, 1, SIGN_HEIGHT)
    board.setLocalPosition(0, POLE_HEIGHT + SIGN_HEIGHT / 2, 0)
    board.setLocalEulerAngles(90, 0, 0) // face forward (plane default is horizontal)

    // Create text texture
    const texture = ZoneSign.createTextTexture(app.graphicsDevice, label)
    const boardMat = new pc.StandardMaterial()
    boardMat.diffuseMap = texture
    boardMat.metalness = 0
    boardMat.gloss = 0.05
    boardMat.cull = pc.CULLFACE_NONE // visible from both sides
    boardMat.update()
    board.render!.meshInstances[0].material = boardMat

    root.addChild(board)
    return root
  }

  /** Render text onto a canvas, return as pc.Texture. */
  private static createTextTexture(device: pc.GraphicsDevice, text: string): pc.Texture {
    const canvas = document.createElement('canvas')
    canvas.width = TEX_W
    canvas.height = TEX_H
    const ctx = canvas.getContext('2d')!

    // Warm brown background with border
    ctx.fillStyle = '#6B4226'
    ctx.fillRect(0, 0, TEX_W, TEX_H)
    ctx.strokeStyle = '#4A2F1A'
    ctx.lineWidth = 4
    ctx.strokeRect(2, 2, TEX_W - 4, TEX_H - 4)

    // White text
    ctx.fillStyle = '#F5E6D0'
    ctx.font = 'bold 28px "Segoe UI", Arial, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(text, TEX_W / 2, TEX_H / 2)

    const texture = new pc.Texture(device, {
      width: TEX_W,
      height: TEX_H,
      format: pc.PIXELFORMAT_RGBA8,
      minFilter: pc.FILTER_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })

    const pixels = texture.lock()
    const imageData = ctx.getImageData(0, 0, TEX_W, TEX_H)
    pixels.set(imageData.data)
    texture.unlock()

    return texture
  }
}
