# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Sandbox merge engine — mirrors ``phase_b3_merge`` shape against xlm_* tables.

Three pieces:

- ``cluster`` — pgvector-cosine + same-title union-find, returns
  :class:`MergeCluster` rows.
- ``promote`` — sole writer of ``xlm_knowledge_item`` rows; ports
  ``app.services.merge_writer.promote_synth_to_ki`` semantics.
- ``runner`` — orchestrator: cluster → singleton-promote → Claude on
  multi-member clusters → orphan-rescue audit.
"""
