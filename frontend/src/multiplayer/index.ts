// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Multiplayer module — Colyseus-based real-time sync.
 *
 * Public API:
 *   ColyseusClient  — singleton WebSocket connection manager
 *   OrgRoomClient   — higher-level org-wide state subscription
 *   NetworkedPlayer  — remote player avatar entity
 *   PlayerSyncAdapter — throttled position broadcaster
 */
export { ColyseusClient, type PlayerData, type MultiplayerCallbacks } from './ColyseusClient'
export { NetworkedPlayer } from './NetworkedPlayer'
export { PlayerSyncAdapter } from './PlayerSyncAdapter'
export {
  OrgRoomClient,
  type MemberStateSnapshot,
  type AgentStateSnapshot,
  type MemberChangeListener,
} from './OrgRoomClient'
