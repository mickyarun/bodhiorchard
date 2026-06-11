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
    trackShape: 'straight',      // or 'circuit' (one lap; distance = circumference)
    cameraMode: 'participant',   // or 'spectator'
    racers: [{ id, name, config, laneIndex }, ...],
    leaderProvider: () => leaderArcM,
  },
})

// Drive avatar kinematics per frame from the client's state snapshot
engine.setRacerKinematics(racerId, positionM, velocityMps, isSprinting)

engine.resize(width, height)
engine.destroy()
```

## Architecture

- `TrackProjection` maps the physics' 1-D `positionM` scalar onto world
  space: `StraightProjection` (arc = X, lateral = Z) or
  `CircuitProjection` (wraps `@shared/race/CircuitGeometry`; the race
  distance is the lap circumference). Avatars, pads, hurdles and the
  chase camera all place themselves through it.
- `RaceSceneTrack.buildTrackAssembly` owns the per-shape surface stack:
  straight → `TrackBuilder` / `Ground` / `FinishArch` / `DecorBuilder`;
  circuit → `CircuitTrackBuilder` (loop ribbons via `RibbonMesh` over `LoopPath`) +
  ring-sized ground + arch at arc = circumference. Track width scales
  with `racerCount × LANE_WIDTH_M` so a 2-racer sprint and a 10-racer
  dash share the same code path.
- `RaceCamera` (participant) chases the tracked racer along the travel
  tangent. `RaceCameraOverhead` (spectator) is a fixed camera — over the
  straight midpoint, or over the circuit's centre at a height that fits
  the ring. `RaceScene` picks one at build time based on `cameraMode`.
- `RacerAvatar` is the KayKit-backed avatar per racer; its kinematics are
  driven by the client each frame via `RaceScene.setRacerKinematics`,
  with the anim graph state machine split into `RacerAvatarAnim`.
- Physics lives in `@shared/race/RacePhysics` — pure TS, imported by both
  `RaceRoom` (server authority) and the frontend tests. No framework.
  It is shape-agnostic: on a circuit the scalar is arc length.

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
