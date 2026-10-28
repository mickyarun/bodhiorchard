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
 * Shared body of every room's `onUncaughtException`.
 *
 * Without that hook Colyseus calls message handlers, clock timers and the
 * simulation interval unwrapped, so one throwing handler escapes the
 * WebSocket listener and exits the Node process, dropping every room for
 * every org. Defining the hook makes Colyseus wrap them: the error is
 * reported here and the room carries on. Lifecycle methods (onCreate,
 * onAuth, onJoin, onLeave) are still rethrown by Colyseus after this runs,
 * so a rejected join stays rejected.
 */
import type { Room, RoomException, RoomMethodName } from "colyseus"
import { safeLog } from "../bridge/logSanitize"

/** Stack lines kept in a report; safeLog caps each line, not the whole stack. */
const MAX_STACK_LINES = 15

export function reportRoomException(
  room: Room,
  error: RoomException,
  methodName: RoomMethodName,
): void {
  // A rejected onAuth is a normal outcome (bad or expired token) that the
  // client already receives; logging it as a crash would be noise.
  if (methodName === "onAuth") return
  console.error(
    "[%s %s] uncaught error in %s: %s %s",
    room.constructor.name,
    safeLog(room.roomId),
    methodName,
    safeLog(error.message),
    sanitisedStack(error),
  )
}

/**
 * Stack of the error the handler actually threw, as one log-safe line.
 * Colyseus wraps it in a RoomException whose own stack only points at the
 * wrapper, and whose other fields carry the client and the raw message
 * payload, so the exception object itself is never logged. Each frame is
 * sanitised on its own so the per-value length cap does not cut the stack
 * down to its first few frames.
 */
function sanitisedStack(error: RoomException): string {
  const { cause } = error as { cause?: unknown }
  const thrown = cause instanceof Error ? cause : error
  const stack = thrown.stack ?? thrown.message
  return stack
    .split("\n")
    .slice(0, MAX_STACK_LINES)
    .map((line) => safeLog(line.trim()))
    .join(" | ")
}
