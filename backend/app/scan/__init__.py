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
