# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Claude synthesis for the pipeline.

* :mod:`prompt` builds the direct-payload synthesis prompt embedding
  the reduced meta-community list as JSON.
* :mod:`runner` defines the ``SynthesisEngine`` protocol with one
  Claude-CLI implementation. Reuses ``app/services/claude_runner.py``.
"""
