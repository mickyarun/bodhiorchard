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
 * RaceRoomHelpers — pure parsers + schema-adapters used by RaceRoom.
 *
 * Kept separate so `RaceRoom.ts` stays under the 300-line hard cap and
 * so the parsers can be unit-tested without spinning up Colyseus.
 */
import type { Racer } from "../../../shared/race/RacePhysics"
import type { Placing, TrackShape } from "../../../shared/race/types"
import { ALLOWED_TRACK_SHAPES, MAX_RACERS } from "../../../shared/race/RaceConstants"
import { PlacingState } from "../schema/PlacingState"
import { RacerState } from "../schema/RacerState"
import type { RaceResultsPayload, RaceResultsPlacing } from "../bridge/BackendClient"

export interface RaceCreateOptions {
  orgId: string
  hostUserId: string
  hostName: string
  distanceM: number
  trackShape: TrackShape
  invitedUserIds: string[]
  /** Dev-mode test bots to seed (0 in production — see resolveBotCount). */
  botCount: number
}

/** Race-identifying fields forwarded onto every results-POST payload. */
export interface RaceResultsHeader {
  roomId: string
  orgId: string
  hostUserId: string
  distanceM: number
}

/**
 * Parse + validate the options passed into `onCreate`.
 *
 * Colyseus forwards whatever the caller supplies to `matchMaker.createRoom`
 * — so the server must defend in depth against malformed or malicious
 * payloads even though the OrgRoom handler is the only intended caller.
 */
export function assertRaceCreateOptions(
  raw: unknown,
  allowedDistances: readonly number[],
): RaceCreateOptions {
  if (typeof raw !== "object" || raw === null) {
    throw new Error("RaceRoom.onCreate: options must be an object")
  }
  const o = raw as Record<string, unknown>

  const orgId = asString(o.orgId, "orgId")
  const hostUserId = asString(o.hostUserId, "hostUserId")
  const hostName = asString(o.hostName, "hostName")
  const distanceM = asNumber(o.distanceM, "distanceM")
  if (!allowedDistances.includes(distanceM)) {
    throw new Error(
      `RaceRoom.onCreate: distanceM=${distanceM} not in ${allowedDistances.join("/")}`,
    )
  }
  const trackShape = asTrackShape(o.trackShape)
  const invited = Array.isArray(o.invitedUserIds) ? o.invitedUserIds : []
  const invitedUserIds: string[] = []
  for (const v of invited) {
    if (typeof v === "string" && v.length > 0) invitedUserIds.push(v)
  }
  const botCount = resolveBotCount(o.botCount, isProductionServer())
  return { orgId, hostUserId, hostName, distanceM, trackShape, invitedUserIds, botCount }
}

/**
 * Resolve the dev-mode bot count from an untrusted payload field.
 *
 * Bot racers are a local development aid only, and the gate lives HERE,
 * server-side: whatever a client sends, a production server forces 0 so
 * bots can never occupy lanes in a real org's race (their synthetic user
 * ids must never approach the backend). On non-production servers the
 * value clamps to [0, MAX_RACERS − 1], always leaving a lane for the
 * human host. Anything non-numeric resolves to 0.
 */
export function resolveBotCount(raw: unknown, isProduction: boolean): number {
  if (isProduction) return 0
  if (typeof raw !== "number" || !Number.isFinite(raw)) return 0
  const n = Math.trunc(raw)
  return Math.max(0, Math.min(MAX_RACERS - 1, n))
}

/** Named environment gate for resolveBotCount — see its docstring. */
export function isProductionServer(): boolean {
  return process.env.NODE_ENV === "production"
}

/**
 * Bot identification policy — ONE mechanism, used everywhere: bot user
 * ids carry the `bot-` prefix. Real user ids are backend-issued UUIDs,
 * so the prefix cannot collide. `RacerState.isBot` mirrors this for
 * clients; `buildRaceResultsPayload` keys off it to keep bots out of the
 * backend POST (bot ids would violate the results table's user FKs).
 */
export const BOT_USER_ID_PREFIX = "bot-"

export function isBotUserId(userId: string): boolean {
  return userId.startsWith(BOT_USER_ID_PREFIX)
}

/**
 * Fixed, valid character encodings for bots, cycled by bot number —
 * parseCharacterModel's "kaykit:{id}:{shirt}:{pants}:{skin}:{rh}:{lh}"
 * format, so the client spawns real avatars instead of fallbacks.
 */
const BOT_CHARACTER_MODELS: readonly string[] = [
  "kaykit:barbarian:E63946:1D3557:F4C28F::",
  "kaykit:mage:457B9D:2B2D42:C68642::",
  "kaykit:knight:F4A261:264653:F4C28F::",
  "kaykit:ranger:2A9D8F:3A2E2A:8D5524::",
  "kaykit:rogue:9B5DE5:22223B:F4C28F::",
  "kaykit:rogue_hooded:FFD75E:283618:C68642::",
  "kaykit:barbarian:30D66D:0D1422:F4C28F::",
]

/**
 * Seed one bot's schema state. Bots are `connected` from birth (no
 * client will ever join for them) so they count toward MIN_RACERS and
 * the lobby renders them as ready — host + one bot can start a race.
 */
export function buildBotRacerState(botNumber: number, laneIndex: number): RacerState {
  const id = `${BOT_USER_ID_PREFIX}${botNumber}`
  const state = new RacerState()
  state.id = id
  state.userId = id
  state.name = `Bot ${botNumber}`
  state.characterModel = BOT_CHARACTER_MODELS[(botNumber - 1) % BOT_CHARACTER_MODELS.length]
  state.laneIndex = laneIndex
  state.isBot = true
  state.connected = true
  return state
}

/**
 * `trackShape` is optional for backward compatibility with pre-circuit
 * clients — absent means 'straight'. A *present* but unknown value is a
 * hard error, same defence-in-depth stance as the distance check above.
 */
function asTrackShape(v: unknown): TrackShape {
  if (v === undefined || v === null) return "straight"
  if (typeof v === "string" && (ALLOWED_TRACK_SHAPES as readonly string[]).includes(v)) {
    return v as TrackShape
  }
  throw new Error(
    `RaceRoom.onCreate: trackShape=${String(v)} not in ${ALLOWED_TRACK_SHAPES.join("/")}`,
  )
}

/**
 * Parse a `race_join` message payload and promote it to a freshly
 * initialised `RacerState`. Returns `null` on invalid payloads — RaceRoom
 * treats that as a no-op so a buggy client can't crash the room.
 */
export function buildRacerState(raw: unknown, laneIndex: number): RacerState | null {
  if (typeof raw !== "object" || raw === null) return null
  const o = raw as Record<string, unknown>
  const userId = optionalString(o.userId)
  const name = optionalString(o.name)
  if (!userId || !name) return null
  const state = new RacerState()
  state.id = userId
  state.userId = userId
  state.name = name
  state.characterModel = optionalString(o.characterModel) ?? ""
  state.laneIndex = laneIndex
  return state
}

/**
 * Copy mutable physics fields onto the synced schema state. Invariant
 * fields (id, userId, name, characterModel, laneIndex, connected) are
 * never touched — they're set once at join time.
 */
export function copyRacerToSchema(phys: Racer, schema: RacerState): void {
  schema.positionM = phys.positionM
  schema.velocityMps = phys.velocityMps
  schema.finished = phys.finished
  schema.finishTimeMs = phys.finishTimeMs
  schema.isMoving = phys.isMoving
  schema.sprintUntilMs = phys.sprintUntilMs
  schema.staminaPct = phys.staminaPct
  schema.boostUntilMs = phys.boostUntilMs
  schema.jumpUntilMs = phys.jumpUntilMs
  schema.knockdownUntilMs = phys.knockdownUntilMs
}

function asString(v: unknown, name: string): string {
  if (typeof v !== "string" || v.length === 0) {
    throw new Error(`RaceRoom.onCreate: ${name} must be a non-empty string`)
  }
  return v
}

function asNumber(v: unknown, name: string): number {
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new Error(`RaceRoom.onCreate: ${name} must be a finite number`)
  }
  return v
}

function optionalString(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null
}

/**
 * Promote a pure-physics `Placing` to its Colyseus-synced schema mirror.
 *
 * Schema construction lives here (not in RaceRoom) so RaceRoom keeps its
 * orchestration role and the field-by-field mapping is unit-testable.
 */
export function placingToSchema(p: Placing): PlacingState {
  const s = new PlacingState()
  s.racerId = p.racerId
  s.place = p.place
  s.finished = p.finished
  s.finishTimeMs = p.finishTimeMs
  s.distanceM = p.distanceM
  return s
}

/**
 * Build the JSON payload posted to the backend on race dispose.
 *
 * Returns `null` when there's nothing meaningful to persist:
 *   - empty placings (room disposed before `finishRound` ever ran)
 *   - placings with zero finishers (room disposed mid-race with everyone DNF)
 *
 * Extracted from `RaceRoom.onDispose` so the multi-finisher contract is
 * lockable in vitest — the test suite proves that **every** placing
 * passed in surfaces in the outgoing payload, finishers and DNFs alike.
 * A regression here is what would produce the "only winner appears on
 * the leaderboard" symptom, so the test is the canary.
 *
 * Dev-mode bots (isBotUserId) are excluded entirely: their synthetic
 * ids aren't real users, so a row for them would violate the backend's
 * user FKs — and the "any finisher" decision below is therefore made
 * over HUMAN placings only. A round where only bots crossed the line
 * persists nothing. Bots still appear in the in-room placings schema,
 * so the podium UI shows them.
 */
export function buildRaceResultsPayload(
  header: RaceResultsHeader,
  placings: Iterable<PlacingState>,
): RaceResultsPayload | null {
  const rows: RaceResultsPlacing[] = []
  let anyFinisher = false
  for (const p of placings) {
    if (isBotUserId(p.racerId)) continue
    rows.push({
      userId: p.racerId,
      finishTimeMs: p.finished ? p.finishTimeMs : null,
      place: p.place,
      finished: p.finished,
      distanceMReached: p.distanceM,
      distanceM: header.distanceM,
    })
    if (p.finished) anyFinisher = true
  }
  if (rows.length === 0 || !anyFinisher) return null
  return {
    roomId: header.roomId,
    orgId: header.orgId,
    hostUserId: header.hostUserId,
    distanceM: header.distanceM,
    placings: rows,
  }
}

// ─── in-room message parsers ─────────────────────
//
// Pure payload validation for RaceRoom's onMessage handlers, kept here
// (with the other parsers) so RaceRoom.ts stays orchestration-only and
// the validation rules are unit-testable without Colyseus.

export interface MoveMsg {
  userId: string
  isMoving: boolean
}

export function parseMove(raw: unknown): MoveMsg | null {
  if (typeof raw !== "object" || raw === null) return null
  const o = raw as Record<string, unknown>
  if (typeof o.userId !== "string" || typeof o.isMoving !== "boolean") return null
  return { userId: o.userId, isMoving: o.isMoving }
}

export function parseUserIdOnly(raw: unknown): string | null {
  if (typeof raw !== "object" || raw === null) return null
  const o = raw as Record<string, unknown>
  return typeof o.userId === "string" ? o.userId : null
}

/**
 * Parse a `race_add_invitees` payload into a clean string array.
 * Drops empty / non-string entries silently so a buggy client can't
 * push junk into `state.invitedUserIds`.
 */
export function parseAddInviteesPayload(raw: unknown): string[] {
  if (typeof raw !== "object" || raw === null) return []
  const o = raw as Record<string, unknown>
  const arr = o.userIds
  if (!Array.isArray(arr)) return []
  const out: string[] = []
  for (const v of arr) {
    if (typeof v === "string" && v.length > 0) out.push(v)
  }
  return out
}
