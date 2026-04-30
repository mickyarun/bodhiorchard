# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Scan pipeline utility package — audit, context, prompts, sessions.

Cross-cutting helpers consumed by ``app.services.scan`` (orchestrator
+ stages + phase implementations). The orchestration layer lives at
``app.services.scan``; this package only holds the support modules.

Module surface:
- ``app.scan.context`` — ``ScanContext`` carrier shared across phases
- ``app.scan.session`` — ``with_session`` / ``gather_repos`` async-pool helpers
- ``app.scan.prompts`` — ``build_synthesis_prompt`` / ``build_merge_prompt`` /
  ``build_direct_scan_prompt`` Claude prompt templates
- ``app.scan.audit`` — ``audit_scan`` post-scan integrity check
- ``app.scan.soft_delete`` — ``soft_delete_for_changed_repos`` /
  ``rollback_soft_deleted_features`` data-safety helpers
"""
