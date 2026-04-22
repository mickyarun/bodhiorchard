// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Coffee bar interior module — public API for GardenEngine.
 *
 * Only CoffeeBarManager leaks to callers; internal scene / UI / room-client
 * classes stay behind this boundary.
 */
export { CoffeeBarManager, type CoffeeBarVisitor } from './CoffeeBarManager'
