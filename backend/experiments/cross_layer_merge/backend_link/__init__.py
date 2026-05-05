# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Endpoint-grounded cross-layer linker for the merge sandbox.

Public entrypoint is :func:`runner.run_backend_link` — exposed via
``run.py``'s ``backend-link`` CLI command.
"""

from experiments.cross_layer_merge.backend_link.runner import (
    BackendLinkSummary,
    run_backend_link,
)

__all__ = ["BackendLinkSummary", "run_backend_link"]
