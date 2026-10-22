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

/** Birthday and work-anniversary announcement settings. */

/** What happens to a celebration that falls on a non-posting day. */
export type WeekendPolicy = 'skip' | 'roll_forward' | 'roll_backward'

/** Giphy content-rating ceiling. */
export type GifRating = 'g' | 'pg' | 'pg-13'

export interface CelebrationSettings {
  enabled: boolean
  /** Slack channel ID (`C...`), not a `#name`. The bot must be a member. */
  slackChannelId: string | null
  /** `HH:MM`, 24-hour, in `timezone`. */
  postTime: string
  /** IANA name; `null` means the server's own zone. */
  timezone: string | null
  /** Python `weekday()` ints — Mon=0 … Sun=6. */
  activeWeekdays: number[]
  weekendPolicy: WeekendPolicy
  includeBirthdays: boolean
  includeAnniversaries: boolean
  mentionChannel: boolean
  gifEnabled: boolean
  gifRating: GifRating
  gifTags: string[]
}

/** Result of the "send a test post" action — a labelled sample, never a real post. */
export interface CelebrationTestResult {
  posted: boolean
  /**
   * `sent`, or why nothing was posted: `no_channel`, `no_slack_token`,
   * `token_decrypt_failed`, or `slack:<code>` with Slack's own error.
   */
  detail: string
}

/** How many people the feature will announce. Counts only, never names. */
export interface CelebrationAudience {
  birthdays: number
  anniversaries: number
}

/** Outcome of pulling profile photos from Slack. */
export interface SlackAvatarSyncResult {
  updated: number
  skipped_no_photo: number
  skipped_has_photo: number
}
