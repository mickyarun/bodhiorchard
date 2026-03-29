/**
 * Multiplayer module — Colyseus-based real-time sync.
 *
 * Public API:
 *   ColyseusClient  — singleton WebSocket connection manager
 *   NetworkedPlayer  — remote player avatar entity
 *   PlayerSyncAdapter — throttled position broadcaster
 */
export { ColyseusClient, type PlayerData, type MultiplayerCallbacks } from './ColyseusClient'
export { NetworkedPlayer } from './NetworkedPlayer'
export { PlayerSyncAdapter } from './PlayerSyncAdapter'
