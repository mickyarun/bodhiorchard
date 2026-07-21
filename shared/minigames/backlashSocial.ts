// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

export const BACKLASH_ENCOURAGEMENTS = ["👏", "🔥", "🎉", "💪", "😭"] as const

export type BacklashEncouragement = typeof BACKLASH_ENCOURAGEMENTS[number]

export const BACKLASH_ENCOURAGEMENT_COOLDOWN_MS = 1_500
export const BACKLASH_MAX_VIEWERS = 24
export const BACKLASH_LIVE_PHASES = ["playing", "jump", "promotion"] as const

export type BacklashLivePhase = typeof BACKLASH_LIVE_PHASES[number]

export function isBacklashEncouragement(value: unknown): value is BacklashEncouragement {
  return typeof value === "string"
    && (BACKLASH_ENCOURAGEMENTS as readonly string[]).includes(value)
}

export function isBacklashLivePhase(value: unknown): value is BacklashLivePhase {
  return typeof value === "string"
    && (BACKLASH_LIVE_PHASES as readonly string[]).includes(value)
}
