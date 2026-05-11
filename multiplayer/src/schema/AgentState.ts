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
 * AgentState — server-authoritative state for one agent/robot character.
 *
 * Agents are spawned by skill_invoked events and despawned by skill_completed.
 * Walking and work animations are driven server-side and synced to clients.
 */
import { Schema, type } from "@colyseus/schema"

export class AgentState extends Schema {
  // Identity
  @type("string") agentId = ""           // task_id or unique key
  @type("string") skillSlug = ""
  @type("string") skillName = ""
  @type("string") actorName = ""

  // Target
  @type("string") repoName = ""          // current repo tree
  @type("number") budNumber = 0

  // Position
  @type("number") x = 0
  @type("number") y = 0
  @type("number") z = 0
  @type("number") yaw = 0

  // Animation state: spawning | walking | working | completing | fading | done
  @type("string") state = "spawning"
  @type("string") action = ""            // current work action (grab/spin/miniguns)

  // Label
  @type("string") message = ""           // e.g., "Analyzing code..."
}
