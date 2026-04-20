// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { describe, it, expect, vi } from 'vitest'
import type * as pc from 'playcanvas'
import { disposeEntity, safeDestroyMaterial, safeDestroyTexture } from './dispose'

/**
 * These tests cover the guard behaviour — no PlayCanvas graphics device is
 * created; we pass in plain objects shaped like `pc.Texture` /
 * `pc.StandardMaterial` / `pc.Entity` that record `.destroy()` calls.
 */

function makeFakeTexture(): pc.Texture {
  return { destroy: vi.fn() } as unknown as pc.Texture
}

function makeFakeMaterial(): pc.StandardMaterial {
  return {
    diffuseMap: {} as pc.Texture,
    emissiveMap: {} as pc.Texture,
    normalMap: {} as pc.Texture,
    opacityMap: {} as pc.Texture,
    update: vi.fn(),
    destroy: vi.fn(),
  } as unknown as pc.StandardMaterial
}

function makeFakeEntity(): pc.Entity {
  return { destroy: vi.fn() } as unknown as pc.Entity
}

describe('safeDestroyTexture', () => {
  it('no-op for null / undefined', () => {
    expect(() => safeDestroyTexture(null)).not.toThrow()
    expect(() => safeDestroyTexture(undefined)).not.toThrow()
  })

  it('destroys once; repeat call is a no-op (PlayCanvas double-destroy bug guard)', () => {
    const tex = makeFakeTexture()
    safeDestroyTexture(tex)
    safeDestroyTexture(tex)
    safeDestroyTexture(tex)
    expect(tex.destroy).toHaveBeenCalledTimes(1)
  })

  it('tracks textures independently', () => {
    const a = makeFakeTexture()
    const b = makeFakeTexture()
    safeDestroyTexture(a)
    safeDestroyTexture(b)
    expect(a.destroy).toHaveBeenCalledTimes(1)
    expect(b.destroy).toHaveBeenCalledTimes(1)
  })
})

describe('safeDestroyMaterial', () => {
  it('no-op for null / undefined', () => {
    expect(() => safeDestroyMaterial(null)).not.toThrow()
    expect(() => safeDestroyMaterial(undefined)).not.toThrow()
  })

  it('nulls every map reference, calls update, then destroys', () => {
    const mat = makeFakeMaterial()
    safeDestroyMaterial(mat)

    expect(mat.diffuseMap).toBeNull()
    expect(mat.emissiveMap).toBeNull()
    expect(mat.normalMap).toBeNull()
    expect(mat.opacityMap).toBeNull()
    expect(mat.update).toHaveBeenCalledTimes(1)
    expect(mat.destroy).toHaveBeenCalledTimes(1)
  })

  it('guards against double destroy', () => {
    const mat = makeFakeMaterial()
    safeDestroyMaterial(mat)
    safeDestroyMaterial(mat)
    expect(mat.destroy).toHaveBeenCalledTimes(1)
    expect(mat.update).toHaveBeenCalledTimes(1)
  })
})

describe('disposeEntity', () => {
  it('no-op for null / undefined', () => {
    expect(() => disposeEntity(null)).not.toThrow()
    expect(() => disposeEntity(undefined)).not.toThrow()
  })

  it('calls entity.destroy exactly once', () => {
    const e = makeFakeEntity()
    disposeEntity(e)
    expect(e.destroy).toHaveBeenCalledTimes(1)
  })
})
