// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

export { TakeoverController } from './TakeoverController'
export { TakeoverCamera } from './TakeoverCamera'
export { TakeoverUI } from './TakeoverUI'
export { ProximitySystem } from './ProximitySystem'
export { loadTakeoverAnimations, restoreLocomotionAnimations } from './TakeoverAnimGraph'
export {
  TakeoverPhysicsBuilder,
  type HutInfo,
  type PondObstacle,
  type LocalWallBox,
  computeHutWallBoxes,
  rotatePointYaw,
} from './TakeoverPhysicsBuilder'
