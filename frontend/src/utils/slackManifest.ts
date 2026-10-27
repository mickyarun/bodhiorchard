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
 * The Slack app definition Glideship needs: bot scopes, bot events and
 * the manifest that creates the app in one step. The setup guide lists
 * the same scopes and events, so both read from here.
 */

export const SLACK_BOT_SCOPES = [
  'chat:write',
  'im:write',
  'channels:read',
  'channels:history',
  'channels:join',
  'reactions:read',
  'users:read',
  'users:read.email',
  'groups:history',
] as const

export const SLACK_BOT_EVENTS = ['reaction_added', 'message.channels', 'message.groups'] as const

/** Scopes the member sync needs on top of posting. */
export const SLACK_SYNC_SCOPES = ['users:read', 'users:read.email'] as const

export const SLACK_EVENTS_PATH = '/api/v1/slack/events'

export function slackManifest(): string {
  return JSON.stringify(
    {
      display_information: {
        name: 'Glideship',
        description: 'Glideship code intelligence notifications and agent triggers',
      },
      features: { bot_user: { display_name: 'Glideship', always_online: true } },
      oauth_config: { scopes: { bot: [...SLACK_BOT_SCOPES] } },
      settings: {
        event_subscriptions: { bot_events: [...SLACK_BOT_EVENTS] },
        org_deploy_enabled: false,
        socket_mode_enabled: false,
        token_rotation_enabled: false,
      },
    },
    null,
    2,
  )
}

export function slackEventsUrl(origin: string): string {
  return `${origin}${SLACK_EVENTS_PATH}`
}
