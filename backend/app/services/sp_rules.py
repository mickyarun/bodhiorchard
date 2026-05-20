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

SP_DEV_PR_MERGED = 0.5  # shipped code
SP_DEV_REVIEW_GIVEN = 0.25  # reviewed someone else's PR
SP_DEV_BUD_SHIPPED = 1.0  # BUD reached PROD as assignee
SP_DEV_QUALITY_HIGH = 0.5  # quality effectiveness score > 80
SP_DEV_BUG_TESTING = -0.25  # bug found in testing phase on their BUD
SP_DEV_BUG_PRODUCTION = -1.0  # bug found in production on their BUD

# ─── QA ────────────────────────────────────────

SP_QA_BUGS_BATCH = 1.0  # awarded every N testing bugs filed
SP_QA_BUGS_BATCH_SIZE = 5  # batch size (every 5th bug triggers award)
SP_QA_PROD_BUG_FOUND = 0.5  # caught a production bug
SP_QA_TESTS_COMPLETE = 0.5  # all test cases executed for a BUD
SP_QA_FALSE_POSITIVE = -0.25  # bug closed as invalid

# ─── PM ────────────────────────────────────────

SP_PM_BUD_SHIPPED = 2.0  # BUD they approved reached PROD
SP_PM_BUD_APPROVED_FAST = 0.25  # BUD approved within 1 day of creation
SP_PM_BUD_DISCARDED = -0.5  # BUD discarded (wasted team effort)

# ─── Tech Lead ─────────────────────────────────

SP_TL_REVIEW_DONE = 0.25  # code review completed
SP_TL_ARCH_APPROVED = 0.25  # tech architecture approved
SP_TL_BUD_SHIPPED = 0.5  # BUD reached PROD (as tech lead)
SP_TL_PROD_BUG_MISSED = -0.5  # production bug on BUDs they reviewed

# ─── Designer ──────────────────────────────────

SP_DESIGNER_PHASE_DONE = 0.25  # design phase completed
SP_DESIGNER_BUD_SHIPPED = 0.5  # BUD reached PROD (as contributor)

# ─── Universal (all roles) ─────────────────────

SP_STREAK_14 = 1.0  # 14-day activity streak milestone
SP_STREAK_30 = 2.0  # 30-day activity streak milestone
SP_FIRST_BUD = 1.0  # first BUD contribution (one-time)
SP_LEADERBOARD_TOP3 = 1.0  # top 3 XP leaderboard (weekly)


# ─── Role → BUD Shipped SP mapping ────────────

BUD_SHIPPED_SP: dict[str, float] = {
    "developer": SP_DEV_BUD_SHIPPED,
    "pm": SP_PM_BUD_SHIPPED,
    "designer": SP_DESIGNER_BUD_SHIPPED,
    "tech_lead": SP_TL_BUD_SHIPPED,
}

# ─── Role → Review SP mapping ─────────────────

REVIEW_SP: dict[str, float] = {
    "developer": SP_DEV_REVIEW_GIVEN,
    "tech_lead": SP_TL_REVIEW_DONE,
}
