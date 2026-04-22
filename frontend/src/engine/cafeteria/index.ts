// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Cafeteria interior module — public API for GardenEngine.
 *
 * Only CafeteriaManager leaks to callers; scene / UI / room-client stay
 * behind this boundary, same as the coffee bar module.
 */
export { CafeteriaManager, type CafeteriaVisitor } from './CafeteriaManager'
