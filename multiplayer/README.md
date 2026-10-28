# Glideship Multiplayer Server

Real-time multiplayer server using [Colyseus](https://colyseus.io/) for the Glideship 3D garden.

## Quick Start

```bash
cd multiplayer
npm install
npm run start:dev
```

Server starts on `ws://localhost:2567`.

## Rooms

| Room | Purpose | ID Pattern |
|------|---------|------------|
| `house` | House interior — players see each other inside a house | `house-{memberId}` |
| `garden` | Shared garden world (stub for future) | `garden-{orgId}` |

## Messages

### Client → Server

| Message | Payload | Rate |
|---------|---------|------|
| `move` | `{ x, z, yaw, animState }` | ~20Hz (throttled by client) |

### Server → Client (via state sync)

Player state is synced automatically via Colyseus Schema:

```typescript
class PlayerState {
  userId: string
  name: string
  x: number
  z: number
  yaw: number
  animState: string  // "idle" | "walk" | "sit" | "sleep"
  connected: boolean
}
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm run start:dev` | Dev server with hot reload (ts-node-dev) |
| `npm run start` | Production start (ts-node) |
| `npm run build` | Compile TypeScript to dist/ |
| `npm run start:prod` | Run compiled JS from dist/ |

## Join Authentication

Every room's `onAuth` goes through `src/auth/verifyJoin.ts`. A join needs the
user's JWT as the `token` option; the server verifies it against the backend
(`/api/v1/internal/colyseus/verify-token`) and requires the token's org to be
exactly the room's org. The user id, display name and org a room acts on come
from the backend's answer, never from the other join options.

| Variable | Default | Effect |
|----------|---------|--------|
| `MULTIPLAYER_ALLOW_TOKENLESS_JOIN` | unset | `1` accepts joins without a token, ignored when `NODE_ENV=production`. Such a join must name the room's org as `orgId` and gets the identity `dev:<userId>`, so it never acts as a real member. The frontend always sends a token, so local dev does not need this. |
| `MULTIPLAYER_DEV_MODE` | unset | `1` turns on Colyseus dev mode (rooms restored across restarts). |

The Docker image sets `NODE_ENV=production`.

## Health Check

```bash
curl http://localhost:2567/health
# {"status":"ok","rooms":["house","garden"]}
```

## Architecture

```
multiplayer/
├── src/
│   ├── main.ts              # Server entry point (port 2567)
│   ├── rooms/
│   │   ├── HouseRoom.ts     # Interior multiplayer (max 10 players)
│   │   └── GardenRoom.ts    # Garden multiplayer stub (max 50)
│   └── schema/
│       ├── PlayerState.ts   # Synced player data
│       └── FurnitureState.ts # Future: per-user furniture customization
```

## Frontend Client

The frontend uses `@colyseus/sdk` (singleton at `frontend/src/multiplayer/ColyseusClient.ts`).

Multiplayer is **non-blocking** — the game works offline if this server is not running. The frontend catches connection errors and continues without multiplayer features.
