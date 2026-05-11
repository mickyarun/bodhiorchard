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
 * Format a millisecond duration as a race-style string:
 *   < 1 s        →  "0.12 s"   (tenths)
 *   1–59.99 s    →  "12.34 s"
 *   ≥ 60 s       →  "1:23.45"  (m:ss.hh)
 *   ≥ 60 min     →  "1:02:03.4" (h:mm:ss.h)
 *   ≤ 0          →  "--"
 *
 * Pure — no Date, no Intl, deterministic across runtimes. Tested against
 * every boundary case in `formatTime.test.ts`.
 */
export function formatRaceTime(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "--"

  // Integer-only arithmetic avoids the floating-point precision trap:
  // 12_340 / 1000 = 12.34 exactly but `12.34 - 12 = 0.3399…` floors to 33,
  // not 34. Computing everything from `ms` keeps the output stable.
  const totalMs = Math.floor(ms)
  const totalSec = Math.floor(totalMs / 1000)
  const hundredths = Math.floor(totalMs / 10) % 100
  const tenths = Math.floor(totalMs / 100) % 10

  if (totalSec < 60) {
    return `${totalSec}.${pad2(hundredths)} s`
  }

  if (totalSec < 3600) {
    const min = Math.floor(totalSec / 60)
    const sec = totalSec - min * 60
    return `${min}:${pad2(sec)}.${pad2(hundredths)}`
  }

  const hrs = Math.floor(totalSec / 3600)
  const remainderSec = totalSec - hrs * 3600
  const min = Math.floor(remainderSec / 60)
  const sec = remainderSec - min * 60
  return `${hrs}:${pad2(min)}:${pad2(sec)}.${tenths}`
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}
