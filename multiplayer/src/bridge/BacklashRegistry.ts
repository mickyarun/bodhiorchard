// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

type DeclineHandler = (userId: string) => void

const declineHandlers = new Map<string, DeclineHandler>()

export function registerBacklashDeclineHandler(roomId: string, handler: DeclineHandler): void {
  declineHandlers.set(roomId, handler)
}

export function unregisterBacklashDeclineHandler(roomId: string): void {
  declineHandlers.delete(roomId)
}

export function fireBacklashInviteDeclined(roomId: string, userId: string): boolean {
  const handler = declineHandlers.get(roomId)
  if (!handler) return false
  handler(userId)
  return true
}
