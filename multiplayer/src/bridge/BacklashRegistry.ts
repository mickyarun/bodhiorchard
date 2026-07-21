// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

type DeclineHandler = (userId: string) => void

const declineHandlers = new Map<string, DeclineHandler>()

interface BacklashSummaryHooks {
  onDispose: () => void
  onPhase: (phase: string) => void
  onViewers: (viewerNames: readonly string[]) => void
}

const summaryHooks = new Map<string, BacklashSummaryHooks>()

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

export function registerBacklashSummaryHooks(
  roomId: string,
  hooks: BacklashSummaryHooks,
): void {
  summaryHooks.set(roomId, hooks)
}

export function fireBacklashPhase(roomId: string, phase: string): void {
  const hooks = summaryHooks.get(roomId)
  if (!hooks) return
  runSummaryHook(roomId, "phase", () => hooks.onPhase(phase))
}

export function fireBacklashViewers(roomId: string, viewerNames: readonly string[]): void {
  const hooks = summaryHooks.get(roomId)
  if (!hooks) return
  runSummaryHook(roomId, "viewers", () => hooks.onViewers(viewerNames))
}

export function fireBacklashDispose(roomId: string): void {
  const hooks = summaryHooks.get(roomId)
  if (!hooks) return
  summaryHooks.delete(roomId)
  runSummaryHook(roomId, "dispose", hooks.onDispose)
}

function runSummaryHook(roomId: string, operation: string, callback: () => void): void {
  try {
    callback()
  } catch (error) {
    console.error(
      "[BacklashRegistry] %s hook for room %s failed:",
      operation,
      roomId.replace(/[\r\n]/g, ""),
      error,
    )
  }
}
