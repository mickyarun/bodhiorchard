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
    safeLog(originalStack(error)),
  )
}

/**
 * Stack of the error the handler actually threw. Colyseus wraps it in a
 * RoomException whose own stack only points at the wrapper, and whose other
 * fields carry the client and the raw message payload, so the exception
 * object itself is never logged.
 */
function originalStack(error: RoomException): string | undefined {
  const { cause } = error as { cause?: unknown }
  const thrown = cause instanceof Error ? cause : error
  return thrown.stack ?? thrown.message
}
