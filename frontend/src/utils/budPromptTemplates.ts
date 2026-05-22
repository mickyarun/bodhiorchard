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
 * Shared prompt templates for the three BUD authoring phases.
 *
 * Used by two surfaces:
 *   - BUD detail tabs (Requirements, Design, Tech Spec) — shown inline on
 *     empty sections so the user can copy and paste into their local Claude.
 *   - SettingsMCPConnect.vue — the "Example prompts to start work" panel.
 *
 * The templates accept the BUD's actual ``budNumber`` and ``budId`` so the
 * user never has to substitute placeholders by hand. figmaUrl is optional
 * (tech spec only) — omitting it inserts a ``<PASTE FIGMA URL HERE>`` hint.
 */

// Shared "review-then-commit" gate appended to every prompt. Prevents the
// LLM from writing to the DB on every iteration — the user reviews the full
// draft once in the chat before anything lands.
const REVIEW_GATE = `Important — review-then-commit:
* Compose the full draft and show it to me in the chat.
* Wait for me to say "create it" / "update it" / "looks good, save it"
  (or words to that effect). Do NOT call create_bud / update_bud
  before that explicit confirmation.
* If I ask for changes, iterate on the draft IN THE CHAT — no MCP
  writes mid-iteration.
* Once I confirm, make the single write, show me the server response,
  and stop. Don't keep editing afterwards unless I ask.`

// Recommended local-code-context block for design + tech-spec prompts.
const LOCAL_CODE_CONTEXT_BLOCK = `Local code context (recommended):
* Ask me which local directory holds my checkout, and confirm it's
  on the latest main (e.g. "git pull origin main first"). If I
  don't have a checkout handy, skip this block and continue.
* For each relevant feature from get_features, read its
  'code_locations' — a per-repo map of layer → file paths
  (frontend / backend / processor / etc.). Use YOUR OWN
  filesystem tool to read those files under my checkout; don't
  try to fetch them via the Bodhiorchard MCP (it only exposes
  metadata, not source).
* Ground the spec / design in what those files actually do:
  reuse existing components, name real functions, reference real
  endpoints. Avoid restating implementation that's already there.`

/**
 * PM / PRD update prompt — for updating requirements on an existing BUD.
 */
export function pmUpdatePrompt(budNumber: number | string, budId: string): string {
  return `I want to update the PRD for BUD-${budNumber}.

1. Call get_bud_by_id(bud_id="${budId}") and validate:
   * 'status' == "bud". If not, stop and tell me what status the
     BUD is actually in.
   * 'is_assignee' == true. If false, stop and tell me which user
     ID owns it — only the assignee can update via MCP.
   Do NOT proceed past these checks if either fails.
2. Call get_prompt(task_type="pm") to recall the body shape we expect.
3. Optionally call get_features for new areas the revision touches.
4. Compose the FULL revised Markdown body (not a diff — update_bud
   replaces the field).

${REVIEW_GATE}

When I confirm, call update_bud(bud_id="${budId}", content=<full body>,
expected_phase="bud", linked_feature_ids=[<feature-uuid>, ...]). Show
me the response. If the server returns phase_mismatch, the BUD moved
since your pre-flight read — refetch and reconsider before retrying.`
}

/**
 * Design (UX / wireframe) prompt — for writing or revising a wireframe on an
 * existing BUD in the DESIGN phase.
 */
export function designPrompt(budNumber: number | string, budId: string): string {
  return `I want to write or revise the UX/UI design for BUD-${budNumber}.

The BUD already exists — the design is added by calling update_bud
while the BUD is in the DESIGN phase. There is no separate "create
design" tool; if the design row is empty this still uses update_bud,
and 'create_bud' is reserved for brand-new BUDs in the BUD phase.

1. Call get_bud_by_id(bud_id="${budId}") and validate:
   * 'status' == "design". If not, stop and tell me what status
     the BUD is actually in (design content can only be written while
     the BUD is in the design phase).
   * 'is_assignee' == true. If false, stop and tell me which user
     ID owns it — only the assignee can update via MCP.
   Do NOT proceed past these checks if either fails. Also note
   'impacted_repos' from the response — it may be empty in design
   phase (tech_arch sets it later) but if populated it's the
   BUD-scoped list of repos this design targets.
2. Call list_design_systems() to see every repo that has a design
   system extracted (returns repo_id + repo_name + is_default).
   ALSO call get_bud_designs(bud_id="${budId}") to see which repos
   already have wireframes for this BUD.
3. Pick the target repo:
   * If there's exactly one impacted_repo and it has a design
     system, use that.
   * If get_bud_designs shows existing wireframes you're refining,
     reuse the same repo_id (so the user's existing tab gets
     updated, not a duplicate tab created).
   * Otherwise STOP AND ASK ME which repo to target. List the
     options (repo_name → repo_id) and wait for my pick.
4. Call get_design_system(repo_id="<picked-id>") and use ONLY
   tokens/components from that design system — no ad-hoc colours,
   no new components.
5. Call get_features(query="<area touched by this BUD>") and read
   each result's 'code_locations'. These paths point to existing
   frontend components / views / stores you should reuse rather
   than re-invent.

${LOCAL_CODE_CONTEXT_BLOCK}

6. Call get_prompt(task_type="design") and follow that prompt
   EXACTLY for the wireframe HTML shape.
7. Compose the FULL wireframe HTML (update_bud overwrites the field).

${REVIEW_GATE}

When I confirm, call update_bud(bud_id="${budId}", content=<wireframe
HTML>, expected_phase="design", repo_id="<picked-id>"). repo_id is
REQUIRED — without it the server returns missing_repo_id; with a
mismatched repo it returns repo_not_found. expected_phase guards
against the BUD having moved out of DESIGN since your pre-flight
read. Show me the response (id, bud_number, design_id, repo_id).`
}

/**
 * Tech-arch prompt — for writing or revising the tech spec on an existing BUD
 * in the TECH_ARCH phase. Optionally references a Figma URL if the PM set one.
 */
export function techArchPrompt(
  budNumber: number | string,
  budId: string,
  figmaUrl?: string | null,
): string {
  const figmaLine = figmaUrl
    ? `Figma URL: ${figmaUrl}\n\nIf local Figma MCP tools are available, read frames frame-by-frame\nto understand the user flow before writing the spec.\n`
    : ''

  return `I want to write or revise the tech architecture for BUD-${budNumber}.
${figmaLine}
The BUD already exists — the tech spec is added by calling update_bud
while the BUD is in the TECH_ARCH phase. There is no separate "create
tech spec" tool; 'create_bud' is reserved for brand-new BUDs in the
BUD phase.

1. Call get_bud_by_id(bud_id="${budId}") and validate:
   * 'status' == "tech_arch". If not, stop and tell me what status
     the BUD is actually in (tech_spec can only be written while the
     BUD is in the tech_arch phase).
   * 'is_assignee' == true. If false, stop and tell me which user
     ID owns it — only the assignee can update via MCP.
   Also note whether 'tech_spec_md' is already populated — if so,
   preserve structure when you revise; if empty, this is the first
   spec. Do NOT proceed past the status / assignee checks if either
   fails.
2. Call get_prompt(task_type="tech_plan") and follow that prompt
   EXACTLY for the spec shape.
3. Call get_features(query="<area touched by this BUD>") with
   pagination to see existing capabilities you should reuse or
   extend rather than re-implement. Read each result's
   'code_locations' — a per-repo layer → file-path map pointing at
   the existing implementation files.

${LOCAL_CODE_CONTEXT_BLOCK}

4. Compose the FULL tech-spec Markdown (update_bud replaces the
   field). Use explicit sections for: components touched (reference
   real file paths from code_locations), schema changes, API
   surface, testing strategy, rollout & rollback. End the body with
   the impacted-repos JSON fence the prompt describes — the backend
   parses it.

${REVIEW_GATE}

When I confirm, call update_bud(bud_id="${budId}", content=<tech spec
markdown>, expected_phase="tech_arch", linked_feature_ids=[<feature-uuid>,
...]). The expected_phase param is the safety net — if the BUD moved
out of TECH_ARCH since your pre-flight read, the server returns
phase_mismatch instead of writing your tech spec into the wrong
section. Show me the response (id, bud_number, field, phase,
linked_features).`
}
