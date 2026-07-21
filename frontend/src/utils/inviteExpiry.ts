// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

/** Missing expiry preserves compatibility; malformed or elapsed values fail closed. */
export function isInviteUnexpired(expiresAt: string | undefined, nowMs = Date.now()): boolean {
  if (!expiresAt) return true
  const expiryMs = Date.parse(expiresAt)
  return Number.isFinite(expiryMs) && expiryMs > nowMs
}
