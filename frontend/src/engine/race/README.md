# Race module — v2

Invite-based multi-room race scene. Every race lives in its own Colyseus
`RaceRoom`; the client connects via `RaceRoomClient` and drives this
module's `RaceEngine` / `RaceScene`.

## Public API

```ts
import { RaceEngine } from '@/engine/race'
import { RaceRoomClient } from '@/multiplayer/RaceRoomClient'

const client = new RaceRoomClient()
await client.joinById(roomId, { userId, name, characterModel, token })

const engine = new RaceEngine()
await engine.init(container, {
  width, height,
  scene: {
    distanceM: 100,              // or 200 — only these two are allowed
    racerCount: 4,               // 2..10
    cameraMode: 'participant',   // or 'spectator'
    racers: [{ id, name, config, laneIndex }, ...],
    leaderProvider: () => leaderX,
  },
})

// Drive avatar kinematics per frame from the client's state snapshot
engine.setRacerKinematics(racerId, positionM, velocityMps, isSprinting)

engine.resize(width, height)
engine.destroy()
```

## Architecture

- `TrackBuilder` / `Ground` / `FinishArch` accept `{ distanceM, trackWidthM }`
  at build time; nothing is hardcoded. Track width scales with `racerCount ×
  LANE_WIDTH_M` so a 2-racer sprint and a 10-racer dash share the same code
  path.
- `RaceCamera` (participant) follows the leader. `RaceCameraOverhead`
  (spectator) is a fixed-position top-down camera — no per-frame work.
  `RaceScene` picks one at build time based on `cameraMode`.
- `RacerAvatar` is the KayKit-backed avatar per racer; its kinematics are
  driven by the client each frame via `RaceScene.setRacerKinematics`.
- Physics lives in `@shared/race/RacePhysics` — pure TS, imported by both
  `RaceRoom` (server authority) and the frontend tests. No framework.

## Flow

1. Host meets another member in the garden → proximity panel →
   "Invite to race" → `<RaceSetupDialog>`.
2. Host submits → `OrgRoomClient.sendRaceCreate({ invitedUserIds, distanceM })`
   → `OrgRoom.race_create` creates a `RaceRoom` via `matchMaker.createRoom`,
   fans out invites via `POST /internal/colyseus/race-invite`.
3. Invitees get a persistent notification + live toast
   (`<RaceInviteToast>`). Host and joiners navigate to `/raceview/:roomId`.
4. Host clicks Start → countdown → running. Server ticks `RacePhysics`
   at 20 Hz; clients mirror via schema sync.
5. On finish, `RaceRoom.onDispose` POSTs placings to
   `/internal/colyseus/race-results`. The leaderboard tab reads them via
   `GET /v1/races/leaderboard`.

## Endpoints

- `POST /api/v1/internal/colyseus/race-invite` — bridge-auth, writes one
  `notifications` row + broadcasts via WS `notifications:{userId}` topic.
- `POST /api/v1/internal/colyseus/race-results` — bridge-auth, idempotent
  upsert into `race_results` on `(room_id, user_id)`.
- `GET /api/v1/races/leaderboard?distance=100|200&limit=N` — user-auth,
  org-scoped, returns rows ordered by `finish_time_ms ASC`.

## File-size budget

All files in this module target ≤ 200 lines, hard cap 300. `RaceScene`
sits at ~200; `TrackBuilder` / `FinishArch` / `RacerAvatar` are each
~180. Split by responsibility before growing any file past the cap.
