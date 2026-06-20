# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Skill Point (SP) rules — role-based constants for the SP economy.

SP is a scarce currency earned through quality outcomes, not raw activity.
Unlike XP (earned freely from any dev activity), SP rewards specific
behaviours tied to each role and penalises quality failures.

Target earning rate: ~2-5 SP per week for consistent quality work.
"""

# ─── Developer ─────────────────────────────────

SP_DEV_REVIEW_GIVEN = 0.25  # reviewed someone else's PR
SP_DEV_BUD_SHIPPED = 1.0  # BUD reached PROD as assignee
SP_DEV_QUALITY_HIGH = 0.5  # quality effectiveness score > 80
SP_DEV_BUG_TESTING = -0.25  # bug found in testing phase on their BUD
# Production bug payer (DEFERRED — "bug found in production" for developers is
# not yet wired). When it lands, the penalty for a prod bug filed against a
# shipped Feature (rather than a BUD) is intended to go to the assignee of the
# most recently linked BUD via ``bud_feature_link`` — a heuristic for "who most
# recently changed this feature" without a PR-to-file-path index.
SP_DEV_BUG_PRODUCTION = -1.0  # bug found in production on their BUD or Feature

# ─── QA ────────────────────────────────────────

SP_QA_PROD_BUG_FOUND = 0.5  # production bug they raised is closed (confirmed real)
SP_QA_BUGS_OVER_THRESHOLD = 0.25  # found more testing bugs than the complexity budget
SP_QA_TESTS_COMPLETE = 0.5  # left testing without skipping/overriding any test case
SP_QA_TESTS_OVERRIDDEN = 0.25  # reduced credit when test cases were skipped/overridden
SP_QA_BUG_REJECTED = -0.10  # a bug they raised was rejected as a false positive

# ─── PM ────────────────────────────────────────

SP_PM_REQUIREMENT_TO_DESIGN = 1.0  # PM who first moved the BUD requirement → design
SP_PM_TECHSPEC_ON_TIME = 0.25  # tech spec delivered within the first estimate
# Estimate-vs-actual overrun thresholds (percent) that taper the
# requirement→design credit: above HALF it pays half, above NONE it pays nothing.
SP_PM_SCOPE_VARIATION_HALF_PCT = 30.0
SP_PM_SCOPE_VARIATION_NONE_PCT = 50.0

# ─── Tech Lead ─────────────────────────────────

SP_TL_REVIEW_DONE = 0.25  # code review completed
SP_TL_TECHARCH_ON_TIME = 0.25  # moved the BUD to development within the tech-arch estimate

# ─── Designer ──────────────────────────────────

SP_DESIGNER_CONTRIBUTION = 0.25  # updated the design (figma link / MCP / AI chat)
SP_DESIGNER_ON_TIME_LOW = 0.25  # design delivered on time, low complexity
SP_DESIGNER_ON_TIME_HIGH = 0.5  # design delivered on time, high complexity
SP_DESIGNER_HIGH_COMPLEXITY_MIN = 4  # complexity ≥ this counts as "high" for design

# ─── Universal (all roles) ─────────────────────

SP_STREAK_14 = 0.5  # 14-day activity streak milestone
SP_STREAK_30 = 1.0  # 30-day activity streak milestone

# ─── Role → Review SP mapping ─────────────────

REVIEW_SP: dict[str, float] = {
    "developer": SP_DEV_REVIEW_GIVEN,
    "tech_lead": SP_TL_REVIEW_DONE,
}
