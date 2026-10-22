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

"""Birthday and work-anniversary announcements.

A single digest is posted to one Slack channel per org per local date —
the Billy model — rather than a DM per celebrant. The pieces:

``schedule``
    When a digest fires, and which calendar dates it covers.
``gif``
    Giphy lookup for the celebratory image, always optional.
``compose``
    Slack Block Kit payload for the digest.
``poster``
    Loads celebrants, claims the date, posts.
``scheduler``
    The 60s ``run_forever`` tick registered in ``main.py``.
"""
