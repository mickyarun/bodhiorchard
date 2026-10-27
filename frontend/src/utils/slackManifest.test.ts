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

import { describe, expect, it } from 'vitest'
import { SLACK_BOT_EVENTS, SLACK_BOT_SCOPES, SLACK_SYNC_SCOPES, slackEventsUrl, slackManifest } from './slackManifest'

describe('slackManifest', () => {
  it('carries the same scopes and events the guide lists', () => {
    const manifest = JSON.parse(slackManifest())
    expect(manifest.oauth_config.scopes.bot).toEqual([...SLACK_BOT_SCOPES])
    expect(manifest.settings.event_subscriptions.bot_events).toEqual([...SLACK_BOT_EVENTS])
    expect(manifest.features.bot_user.display_name).toBe('Glideship')
  })
  it('includes the scopes member sync needs', () => {
    for (const scope of SLACK_SYNC_SCOPES) expect(SLACK_BOT_SCOPES).toContain(scope)
  })
})

describe('slackEventsUrl', () => {
  it('points at the events endpoint on this origin', () => {
    expect(slackEventsUrl('https://app.example.com')).toBe('https://app.example.com/api/v1/slack/events')
  })
})
